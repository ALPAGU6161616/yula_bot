from __future__ import annotations

import json
import threading
import time
from queue import Queue
from typing import Any, Dict, Optional

import websocket  # websocket-client


def ccxt_symbol_to_binance_symbol(symbol: str) -> str:
    sym = (symbol or "").strip()
    if not sym:
        return sym
    sym = sym.upper()
    sym = sym.split(":")[0]
    sym = sym.replace("/", "")
    return sym.lower()


class BinanceFuturesKlineStream:
    def __init__(self, symbol: str, interval: str, *, max_queue: int = 2000) -> None:
        self.symbol = ccxt_symbol_to_binance_symbol(symbol)
        self.interval = (interval or "").strip()
        self.queue: "Queue[Dict[str, Any]]" = Queue(maxsize=max_queue)

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws: Optional[websocket.WebSocketApp] = None

        self._last_closed_open_time_ms: Optional[int] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"ws-kline-{self.symbol}-{self.interval}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        self._ws = None

    def _run(self) -> None:
        stream = f"{self.symbol}@kline_{self.interval}"
        url = f"wss://fstream.binance.com/ws/{stream}"

        while not self._stop.is_set():
            self._ws = websocket.WebSocketApp(
                url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            try:
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                pass
            finally:
                self._ws = None

            if not self._stop.is_set():
                time.sleep(2.0)

    def _on_error(self, _ws: websocket.WebSocketApp, _error: Any) -> None:
        # Reconnect loop handles this.
        return

    def _on_close(self, _ws: websocket.WebSocketApp, _close_status_code: Any, _close_msg: Any) -> None:
        # Reconnect loop handles this.
        return

    def _on_message(self, _ws: websocket.WebSocketApp, message: str) -> None:
        try:
            msg = json.loads(message)
        except Exception:
            return

        data = msg.get("data", msg)
        if not isinstance(data, dict):
            return
        if data.get("e") != "kline":
            return

        k = data.get("k")
        if not isinstance(k, dict):
            return

        is_closed = bool(k.get("x"))
        open_time = k.get("t")
        if open_time is None:
            return

        try:
            open_time_ms = int(open_time)
        except Exception:
            return

        if is_closed:
            if self._last_closed_open_time_ms is not None and open_time_ms <= self._last_closed_open_time_ms:
                return
            self._last_closed_open_time_ms = open_time_ms

        try:
            candle = {
                "timestamp_ms": open_time_ms,
                "open": float(k.get("o")),
                "high": float(k.get("h")),
                "low": float(k.get("l")),
                "close": float(k.get("c")),
                "volume": float(k.get("v", 0.0)),
                "closed": is_closed,
            }
        except Exception:
            return

        try:
            self.queue.put_nowait(candle)
        except Exception:
            # queue full -> drop
            return

