from __future__ import annotations

import argparse
import copy
import queue
import signal
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from config import Config
from data_manager import DataManager
from trader import Trader
from yula_strategy import YulaState, YulaStrategy
from binance_ws import BinanceFuturesKlineStream


DEFAULT_TV_PAIRS = ["TAOUSDT.P", "MAVUSDT.P", "MANTAUSDT.P", "ARBUSDT.P", "AAVEUSDT.P"]


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


def _position_amt_from_ccxt_position(pos: dict) -> float:
    if not isinstance(pos, dict):
        return 0.0
    for key in ("contracts", "contractSize", "amount", "positionAmt"):
        try:
            val = pos.get(key)
            if val is None:
                continue
            return float(val)
        except Exception:
            pass
    info = pos.get("info")
    if isinstance(info, dict):
        for key in ("positionAmt", "pa", "positionAmount"):
            try:
                val = info.get(key)
                if val is None:
                    continue
                return float(val)
            except Exception:
                pass
    return 0.0


def _has_open_position(exchange, symbol: str) -> Optional[float]:
    for method_name in ("fetch_positions", "fetch_positions_risk", "fetch_position"):
        method = getattr(exchange, method_name, None)
        if method is None:
            continue
        try:
            if method_name == "fetch_position":
                result = method(symbol)
            elif method_name in ("fetch_positions", "fetch_positions_risk"):
                # Binance USD-M returns only currently open positions when called
                # without symbol filters; if our symbol is missing there, we can
                # safely treat it as flat instead of warning.
                result = method()
            else:
                result = method([symbol])
            if isinstance(result, list):
                result = next((p for p in result if isinstance(p, dict) and p.get("symbol") == symbol), None)
                if result is None and method_name in ("fetch_positions", "fetch_positions_risk"):
                    return 0.0
            amt = _position_amt_from_ccxt_position(result)
            if abs(amt) > 0:
                return amt
            if result is not None:
                return 0.0
        except Exception:
            continue
    return None


@dataclass
class Engine:
    symbol: str
    strategy: YulaStrategy
    state: YulaState
    trader: Trader
    stream: BinanceFuturesKlineStream
    last_processed_ts: Optional[pd.Timestamp]
    next_index: int


POSITION_STATE_FIELDS = (
    "position_size",
    "entry_price",
    "trades",
    "firstTPLevel",
    "secondTPLevel",
    "firstTPHit",
    "secondTPHit",
    "breakevenActive",
    "breakevenLevel",
    "firstTPBar",
    "rangeTrailingStopActive",
    "rangeTrailingStopLevel",
    "activationLevel",
    "trailingProfitStopActive",
    "trailingProfitStopLevel",
    "trailingProfitSystemTriggered",
    "trailingProfitStopTier",
    "highestPriceInPosition",
    "lowestPriceInPosition",
)


def _snapshot_position_state(state: YulaState) -> dict:
    return {field: copy.deepcopy(getattr(state, field, None)) for field in POSITION_STATE_FIELDS}


def _restore_position_state(state: YulaState, snapshot: dict) -> None:
    for field, value in snapshot.items():
        setattr(state, field, copy.deepcopy(value))


def warmup_engine(
    data_manager: DataManager,
    symbol: str,
    timeframe: str,
    history_limit: int,
    *,
    start_from_flat: bool,
    config_overrides: Optional[dict] = None,
) -> tuple[YulaStrategy, YulaState, pd.DataFrame]:
    strategy = YulaStrategy(config_overrides=config_overrides)
    state = YulaState()

    df = data_manager.fetch_initial_data(symbol, timeframe, limit=int(history_limit))
    if df.empty:
        raise RuntimeError(f"No data fetched for warmup: {symbol} {timeframe}")

    latest_closed = data_manager.fetch_latest_candle(symbol, timeframe)
    if latest_closed is not None and "timestamp" in latest_closed:
        df = df[df["timestamp"] <= latest_closed["timestamp"]].reset_index(drop=True)

    for index, row in df.iterrows():
        candle = {
            "timestamp": row["timestamp"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row.get("volume", 0.0),
        }
        strategy.calculate(candle, state, int(index))

    # Start live execution from a clean trade list.
    state.trades = []
    if start_from_flat:
        state.position_size = 0
        state.pendingLongEntry = False
        state.pendingShortEntry = False
        state.pendingEntryBar = None
        state.pendingEntryReason = ""
        strategy._reset_position_state(state)

    return strategy, state, df


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="YULA Bot - multi-pair WS runner (candle close).")
    p.add_argument("--timeframe", default=Config.TIMEFRAME, help="Timeframe, e.g. 15m")
    p.add_argument(
        "--pairs",
        default=",".join(DEFAULT_TV_PAIRS),
        help="Comma-separated pairs (TradingView .P or CCXT).",
    )
    p.add_argument(
        "--start-from-flat",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Start with no position (safe default).",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Allow running when exchange has an open position (advanced).",
    )
    p.add_argument(
        "--history-limit",
        type=int,
        default=Config.HISTORICAL_CANDLE_LIMIT,
        help="Warmup candles per pair.",
    )
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    tv_pairs = [p.strip() for p in (args.pairs or "").split(",") if p.strip()]
    symbols = [tv_perp_to_ccxt_swap_symbol(p) for p in tv_pairs]

    if not symbols:
        print("No pairs provided.")
        return 2

    print("Starting YULA WS runner")
    print(f"Timeframe: {args.timeframe}")
    print(f"Pairs: {', '.join(symbols)}")
    print(f"Live trading: {'ON' if Config.LIVE_TRADING else 'DRY-RUN'}")

    data_manager = DataManager()

    # Safety: If live trading is ON, don't start with an existing open position unless explicitly allowed.
    if Config.LIVE_TRADING and not args.resume:
        for sym in symbols:
            pos_amt = _has_open_position(data_manager.exchange, sym)
            if pos_amt is None:
                print(f"[WARN] Could not check open positions for {sym}.")
                continue
            if abs(pos_amt) > 0:
                print(
                    f"[ERROR] Open position detected for {sym} (amount={pos_amt}). "
                    "Close it first or run with --resume."
                )
                return 3

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
            strategy, state, df = warmup_engine(
                data_manager,
                sym,
                args.timeframe,
                args.history_limit,
                start_from_flat=bool(args.start_from_flat),
            )
            trader = Trader(data_manager.exchange)
            trader.reset()
            stream = BinanceFuturesKlineStream(sym, args.timeframe)
            stream.start()

            last_ts = df["timestamp"].iloc[-1] if not df.empty else None
            next_index = len(df)

            engines[sym] = Engine(
                symbol=sym,
                strategy=strategy,
                state=state,
                trader=trader,
                stream=stream,
                last_processed_ts=last_ts,
                next_index=next_index,
            )
            print(f"[OK] Warmed up {sym} ({len(df)} candles).")
        except Exception as e:
            print(f"[ERROR] Failed to init {sym}: {e}")

    if not engines:
        print("No engines initialized; exiting.")
        return 4

    print("Entering main loop (processing closed candles from WebSocket)...")

    while not stop:
        processed_any = False

        for sym, eng in engines.items():
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

                candle = {
                    "timestamp": ts,
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item.get("volume", 0.0)),
                }

                position_snapshot = _snapshot_position_state(eng.state)
                eng.last_processed_ts = ts
                signal_val, eng.state = eng.strategy.calculate(candle, eng.state, eng.next_index)
                eng.next_index += 1
                if not eng.trader.process_new_trades(eng.state, candle, eng.symbol):
                    _restore_position_state(eng.state, position_snapshot)
                    print(f"[WARN] {sym} order failed; position state rolled back.")

                print(f"[{sym}] {ts} signal={signal_val} trades={len(getattr(eng.state, 'trades', []))}")

        if not processed_any:
            time.sleep(0.2)

    print("Stopping...")
    for eng in engines.values():
        try:
            eng.stream.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
