from __future__ import annotations

import argparse
import queue
import signal
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from binance_ws import BinanceFuturesKlineStream
from config import Config
from data_manager import DataManager
from trader import Trader
from yula_strategy import YulaState


DEFAULT_TV_PAIRS = ["ARUSDT.P", "TAOUSDT.P", "MAVUSDT.P", "MANTAUSDT.P"]


def tv_perp_to_ccxt_swap_symbol(tv_symbol: str) -> str:
    sym = (tv_symbol or "").strip().upper()
    if not sym:
        return tv_symbol
    if "/" in sym:
        base, quote = sym.split("/", 1)
        quote = quote.split(":")[0]
        return f"{base}/{quote}:{quote}"
    if sym.endswith(".P"):
        sym = sym[:-2]
    if sym.endswith("USDT"):
        base = sym[:-4]
        return f"{base}/USDT:USDT"
    return tv_symbol


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke test runner: frequent orders on candle close.")
    p.add_argument("--timeframe", default="1m", help="Timeframe, e.g. 1m")
    p.add_argument("--pairs", default=",".join(DEFAULT_TV_PAIRS), help="Comma-separated pairs (.P or CCXT).")
    p.add_argument(
        "--mode",
        choices=["roundtrip", "flip"],
        default="roundtrip",
        help="roundtrip=ENTRY+EXIT every candle, flip=ENTRY then EXIT next candle.",
    )
    p.add_argument(
        "--direction",
        choices=["alternate", "candle"],
        default="alternate",
        help="alternate=LONG/SHORT alternating, candle=close>=open => LONG else SHORT.",
    )
    p.add_argument("--max-orders", type=int, default=20, help="Stop after placing this many orders (required for live).")
    p.add_argument("--cooldown-ms", type=int, default=200, help="Delay between ENTRY and EXIT in roundtrip mode.")
    p.add_argument("--history-limit", type=int, default=50, help="Warmup REST candles (connection test).")
    p.add_argument("--check-private", action="store_true", help="Call an authenticated endpoint (tests API keys).")
    p.add_argument(
        "--allow-live",
        action="store_true",
        help="Required if LIVE_TRADING=true (prevents accidental mainnet spam).",
    )
    return p.parse_args(argv)


@dataclass
class Engine:
    symbol: str
    trader: Trader
    state: YulaState
    stream: BinanceFuturesKlineStream
    last_processed_ts: Optional[pd.Timestamp]
    next_is_long: bool
    flip_open: bool


def _print_exchange_banner(exchange) -> None:
    try:
        server_time_ms = exchange.fetch_time()
    except Exception:
        server_time_ms = None
    local_ms = int(time.time() * 1000)
    if isinstance(server_time_ms, (int, float)):
        drift = int(local_ms - int(server_time_ms))
        print(f"[TIME] local-ms={local_ms} server-ms={int(server_time_ms)} drift-ms={drift}")
    else:
        print(f"[TIME] local-ms={local_ms} server-ms=unknown")


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    tv_pairs = [p.strip() for p in (args.pairs or "").split(",") if p.strip()]
    symbols = [tv_perp_to_ccxt_swap_symbol(p) for p in tv_pairs]
    if not symbols:
        print("No pairs provided.")
        return 2

    if Config.LIVE_TRADING and not args.allow_live:
        print("[ERROR] LIVE_TRADING=true but --allow-live not set. Refusing to run.")
        print("Set LIVE_TRADING=false for DRY-RUN, or pass --allow-live (and keep max-orders finite).")
        return 3

    if Config.LIVE_TRADING and int(args.max_orders) <= 0:
        print("[ERROR] Refusing to run with LIVE_TRADING=true and --max-orders <= 0 (unlimited).")
        return 4

    print("Starting Smoke Runner")
    print(f"Timeframe: {args.timeframe}")
    print(f"Pairs: {', '.join(symbols)}")
    print(f"Mode: {args.mode}, Direction: {args.direction}")
    print(f"Live trading: {'ON' if Config.LIVE_TRADING else 'DRY-RUN'}  Testnet: {'ON' if Config.USE_TESTNET else 'OFF'}")

    data_manager = DataManager()
    exchange = data_manager.exchange
    try:
        exchange.load_markets()
    except Exception:
        pass

    _print_exchange_banner(exchange)

    if args.check_private:
        try:
            # Any authenticated call is fine; this validates API key permissions.
            exchange.fetch_balance()
            print("[AUTH] fetch_balance OK")
        except Exception as e:
            print(f"[AUTH] fetch_balance FAILED: {e}")

    stop = False

    def _handle_signal(_signum, _frame):
        nonlocal stop
        stop = True

    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except Exception:
        pass

    engines: Dict[str, Engine] = {}
    for sym in symbols:
        try:
            df = data_manager.fetch_initial_data(sym, args.timeframe, limit=int(args.history_limit))
            last_ts = None
            if not df.empty:
                last_ts = df["timestamp"].iloc[-1]

            trader = Trader(exchange)
            trader.reset()
            state = YulaState()
            state.trades = []

            stream = BinanceFuturesKlineStream(sym, args.timeframe)
            stream.start()

            engines[sym] = Engine(
                symbol=sym,
                trader=trader,
                state=state,
                stream=stream,
                last_processed_ts=last_ts,
                next_is_long=True,
                flip_open=False,
            )
            print(f"[OK] Connected {sym} (warmup candles={len(df) if df is not None else 0})")
        except Exception as e:
            print(f"[ERROR] Failed init for {sym}: {e}")

    if not engines:
        print("No engines initialized; exiting.")
        return 5

    total_orders = 0

    def place_trades(eng: Engine, candle: dict) -> int:
        nonlocal total_orders
        ts = candle["timestamp"]
        o = float(candle["open"])
        c = float(candle["close"])

        if args.direction == "candle":
            is_long = c >= o
        else:
            is_long = eng.next_is_long
            eng.next_is_long = not eng.next_is_long

        entry_type = "ENTRY_LONG" if is_long else "ENTRY_SHORT"
        exit_type = "EXIT_TEST"

        made = 0

        if args.mode == "roundtrip":
            eng.state.trades.append({"time": ts, "type": entry_type, "price": c, "size": 1, "comment": "Smoke Entry"})
            eng.state.trades.append({"time": ts, "type": exit_type, "price": c, "size": 1, "comment": "Smoke Exit"})
            eng.trader.process_new_trades(eng.state, candle, eng.symbol)
            made = 2
            if args.cooldown_ms > 0:
                time.sleep(int(args.cooldown_ms) / 1000.0)
        else:
            # flip
            if not eng.flip_open:
                eng.state.trades.append({"time": ts, "type": entry_type, "price": c, "size": 1, "comment": "Smoke Entry"})
                eng.trader.process_new_trades(eng.state, candle, eng.symbol)
                eng.flip_open = True
                made = 1
            else:
                eng.state.trades.append({"time": ts, "type": exit_type, "price": c, "size": 1, "comment": "Smoke Exit"})
                eng.trader.process_new_trades(eng.state, candle, eng.symbol)
                eng.flip_open = False
                made = 1

        total_orders += made
        return made

    print("Listening to WebSocket (processing CLOSED candles only)...")

    while not stop:
        processed_any = False

        for eng in engines.values():
            while True:
                try:
                    item = eng.stream.queue.get_nowait()
                except queue.Empty:
                    break

                processed_any = True
                if not isinstance(item, dict) or not item.get("closed"):
                    continue

                try:
                    ts = pd.to_datetime(int(item["timestamp_ms"]), unit="ms")
                except Exception:
                    continue

                if eng.last_processed_ts is not None and ts <= eng.last_processed_ts:
                    continue
                eng.last_processed_ts = ts

                candle = {
                    "timestamp": ts,
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item.get("volume", 0.0)),
                }

                made = place_trades(eng, candle)
                print(f"[{eng.symbol}] {ts} close={candle['close']} orders+={made} total={total_orders}")

                if int(args.max_orders) > 0 and total_orders >= int(args.max_orders):
                    stop = True
                    break

            if stop:
                break

        if not processed_any:
            time.sleep(0.2)

    print("Stopping smoke runner...")
    for eng in engines.values():
        try:
            eng.stream.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

