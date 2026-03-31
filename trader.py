from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import ccxt
from config import Config


@dataclass
class LivePosition:
    units: float  # Strategy units (signed): + for long, - for short
    qty: float  # Base-asset quantity (positive)


class Trader:
    def __init__(self, exchange):
        self.exchange = exchange
        self.config = Config()
        self._processed_trades = 0
        self._position: Optional[LivePosition] = None
        self._leverage_set_for: set[str] = set()

    def reset(self) -> None:
        self._processed_trades = 0
        self._position = None

    def process_new_trades(self, state, candle: Dict[str, Any], symbol: str) -> None:
        trades: List[Dict[str, Any]] = getattr(state, "trades", [])
        new_trades = trades[self._processed_trades :]
        if not new_trades:
            return

        for trade in new_trades:
            self._handle_trade(trade, candle, symbol)

        self._processed_trades = len(trades)

    def _handle_trade(self, trade: Dict[str, Any], candle: Dict[str, Any], symbol: str) -> None:
        trade_type = trade.get("type")
        if not trade_type:
            return

        if trade_type in {"ENTRY_LONG", "ENTRY_SHORT"}:
            self._ensure_leverage(symbol)
            self._on_entry(trade_type, trade, candle, symbol)
            return

        if trade_type.startswith("EXIT_"):
            self._on_exit(trade_type, trade, candle, symbol)
            return

    def _on_entry(self, trade_type: str, trade: Dict[str, Any], candle: Dict[str, Any], symbol: str) -> None:
        is_long = trade_type == "ENTRY_LONG"
        price = float(trade.get("price") or candle["close"])

        if self._position and self._position.qty > 0:
            # Strategy should not send ENTRY while still in position; ignore to be safe.
            return

        qty = self._calculate_order_qty(symbol, price)
        side = "buy" if is_long else "sell"
        self._place_market_order(symbol, side=side, amount=qty, reduce_only=False, comment=trade.get("comment", trade_type))

        self._position = LivePosition(units=1.0 if is_long else -1.0, qty=qty)

    def _on_exit(self, trade_type: str, trade: Dict[str, Any], candle: Dict[str, Any], symbol: str) -> None:
        if not self._position or self._position.qty <= 0 or self._position.units == 0:
            return

        is_long = self._position.units > 0

        # Partial exits (TP1)
        if trade_type == "EXIT_TP1":
            units_to_close = float(trade.get("size") or 0.0)
            if units_to_close <= 0:
                return

            current_units = abs(self._position.units)
            if current_units <= 0:
                return

            fraction = min(1.0, units_to_close / current_units)
            qty_to_close = self._position.qty * fraction
            self._close_qty(symbol, is_long=is_long, qty=qty_to_close, comment=trade.get("comment", trade_type))

            self._position.qty -= qty_to_close
            if is_long:
                self._position.units -= units_to_close
            else:
                self._position.units += units_to_close

            if self._position.qty <= 0 or abs(self._position.units) <= 1e-9:
                self._position = None
            return

        # Full exits
        self._close_qty(symbol, is_long=is_long, qty=self._position.qty, comment=trade.get("comment", trade_type))
        self._position = None

    def _close_qty(self, symbol: str, is_long: bool, qty: float, comment: str) -> None:
        if qty <= 0:
            return
        side = "sell" if is_long else "buy"
        self._place_market_order(symbol, side=side, amount=qty, reduce_only=True, comment=comment)

    def _ensure_leverage(self, symbol: str) -> None:
        if symbol in self._leverage_set_for:
            return
        self._leverage_set_for.add(symbol)

        if not self.config.LIVE_TRADING:
            return

        leverage = int(getattr(self.config, "LEVERAGE", 1))
        if leverage <= 0:
            return

        try:
            # ccxt supports set_leverage for many futures exchanges.
            if hasattr(self.exchange, "set_leverage"):
                self.exchange.set_leverage(leverage, symbol)
        except Exception:
            pass

    def _calculate_order_qty(self, symbol: str, price: float) -> float:
        notional = float(getattr(self.config, "ORDER_NOTIONAL_USDT", 0.0))
        leverage = float(getattr(self.config, "LEVERAGE", 1.0))
        raw_qty = (notional * leverage) / price if price > 0 else 0.0

        try:
            raw_qty = float(self.exchange.amount_to_precision(symbol, raw_qty))
        except Exception:
            pass

        return max(0.0, raw_qty)

    def _place_market_order(self, symbol: str, side: str, amount: float, reduce_only: bool, comment: str) -> None:
        if amount <= 0:
            return

        if not self.config.LIVE_TRADING:
            print(
                f"[DRY-RUN] {side.upper()} {amount} {symbol} "
                f"(reduceOnly={reduce_only}) - {comment}"
            )
            return

        params: Dict[str, Any] = {}
        if reduce_only:
            params["reduceOnly"] = True

        try:
            self.exchange.create_order(symbol, "market", side, amount, None, params)
        except ccxt.InsufficientFunds as e:
            print(f"[FAIL] {symbol} için işlem açılamadı: Yetersiz Bakiye. ({e})")
        except Exception as e:
            print(f"[ERROR] {symbol} işlem hatası: {e}")

