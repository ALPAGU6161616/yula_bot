import numpy as np
import math
from typing import Optional

import pandas as pd
from config import Config

class YulaState:
    def __init__(self):
        # Price Levels
        self.x1LowPrice = None
        self.y1HighPrice = None
        self.l1LowPrice = None
        self.s1HighPrice = None
        self.m1LowPrice = None
        self.n1HighPrice = None
        
        # Ranges
        self.x_range_high = None
        self.x_range_low = None
        self.y_range_high = None
        self.y_range_low = None
        self.l_range_high = None
        self.l_range_low = None
        self.s_range_high = None
        self.s_range_low = None
        self.m_range_high = None
        self.m_range_low = None
        self.n_range_high = None
        self.n_range_low = None
        
        # Previous Ranges
        self.prev_x_range_high = None
        self.prev_y_range_low = None
        self.prev_s_range_high = None
        self.prev_s_range_low = None
        self.prev_l_range_high = None
        self.prev_l_range_low = None
        
        # Fibonacci Levels
        self.x_fibs = {}
        self.y_fibs = {}
        self.l_fibs = {}
        self.s_fibs = {}
        self.m_fibs = {}
        self.n_fibs = {}
        
        # Conditions
        self.condition_A = False
        self.condition_A1 = False
        self.condition_B = False
        self.condition_B1 = False
        self.condition_C = False
        self.condition_D = False
        self.condition_E = False
        self.condition_F = False
        
        # Active Ranges
        self.x_range_active = False
        self.y_range_active = False
        self.m_range_active = False
        self.n_range_active = False
        
        # Momentum
        self.bullishMomentum = None
        self.bearishMomentum = None
        self.bullishFibMomentum = None
        self.bearishFibMomentum = None
        self.momentumFavorsBullish = False
        self.momentumFavorsBearish = False
        
        # Momentum Tracking
        self.activeBullishMomentumLRangeHigh = None
        self.activeBullishMomentumLRangeLow = None
        self.activeBearishMomentumSRangeHigh = None
        self.activeBearishMomentumSRangeLow = None
        self.bullishMomentumStartBar = None
        self.bullishMomentumEndBar = None
        self.bearishMomentumStartBar = None
        self.bearishMomentumEndBar = None
        self.bullishFibMomentumStartBar = None
        self.bullishFibMomentumEndBar = None
        self.bearishFibMomentumStartBar = None
        self.bearishFibMomentumEndBar = None
        
        # Bar Indices
        self.lastL1BarIndex = None
        self.lastL2BarIndex = None
        self.lastS1BarIndex = None
        self.lastS2BarIndex = None
        self.validL2BarIndex = None
        self.validS2BarIndex = None
        self.validM2BarIndex = None
        self.validN2BarIndex = None
        self.lastL2FormationBar = None
        self.lastS2FormationBar = None
        self.lastBullishMomentumBar = None
        self.lastBearishMomentumBar = None

        # L2 -> M2 / S2 -> N2 tracking
        self.m2FormedAfterL2 = False
        self.n2FormedAfterS2 = False
        
        # Touch Tracking Arrays
        self.latestXongPrices = [None] * 3
        self.latestXongBars = [None] * 3
        self.xongTouchCount = 0
        self.x2CandidatePrices = []
        self.x2CandidateBars = []
        
        self.latestYhortPrices = [None] * 3
        self.latestYhortBars = [None] * 3
        self.yhortTouchCount = 0
        self.y2CandidatePrices = []
        self.y2CandidateBars = []
        
        self.latestLongPrices = [None] * 3
        self.latestLongBars = [None] * 3
        self.longTouchCount = 0
        self.l2CandidatePrices = []
        self.l2CandidateBars = []
        
        self.latestShortPrices = [None] * 3
        self.latestShortBars = [None] * 3
        self.shortTouchCount = 0
        self.s2CandidatePrices = []
        self.s2CandidateBars = []
        
        self.latestMongPrices = [None] * 3
        self.latestMongBars = [None] * 3
        self.mongTouchCount = 0
        self.m2CandidatePrices = []
        self.m2CandidateBars = []
        
        self.latestNhortPrices = [None] * 3
        self.latestNhortBars = [None] * 3
        self.nhortTouchCount = 0
        self.n2CandidatePrices = []
        self.n2CandidateBars = []
        
        # Pending Entry
        self.pendingLongEntry = False
        self.pendingShortEntry = False
        self.pendingEntryBar = None
        self.pendingEntryReason = ""
        
        # Break Tracking
        self.lastBreakIsSRangeHigh = False
        self.lastBreakIsLRangeLow = False
        
        # Used Momentum Tracking (to prevent multiple entries on same range)
        self.usedBullishMomentumBar = None
        self.usedBearishMomentumBar = None

        # --- POSITION MANAGEMENT ---
        self.position_size = 0 # >0 Long, <0 Short, 0 Flat
        self.entry_price = None
        self.trades = [] # List of dictionaries: {'time':, 'type':, 'price':, 'size':, 'comment':}
        
        # TP/SL State
        self.firstTPLevel = None
        self.secondTPLevel = None
        self.firstTPHit = False
        self.secondTPHit = False
        
        self.breakevenActive = False
        self.breakevenLevel = None
        self.firstTPBar = None
        
        self.rangeTrailingStopActive = False
        self.rangeTrailingStopLevel = None
        self.activationLevel = None
        
        self.trailingProfitStopActive = False
        self.trailingProfitStopLevel = None
        self.trailingProfitSystemTriggered = False
        self.trailingProfitStopTier = 0
        
        self.highestPriceInPosition = None
        self.lowestPriceInPosition = None


class YulaStrategy:
    def __init__(self, config_overrides=None):
        self.config = Config()
        if config_overrides:
            for key, value in config_overrides.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
    def _check_time_filters(self, candle):
        timestamp = candle["timestamp"]
        if not isinstance(timestamp, pd.Timestamp):
            timestamp = pd.to_datetime(timestamp, unit="ms")

        # PineScript uses GMT+3 for day/month/hour filters.
        # Binance OHLCV timestamps are UTC; shift by +3 hours to match.
        ts = timestamp
        if isinstance(ts, pd.Timestamp) and ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        ts_gmt3 = ts + pd.Timedelta(hours=3)
            
        # Day Filter
        if self.config.ENABLE_DAY_FILTER:
            # Pine: 1=Sunday ... 7=Saturday
            dow_pine = ((ts_gmt3.dayofweek + 1) % 7) + 1
            allowed = {
                1: self.config.TRADE_ON_SUNDAY,
                2: self.config.TRADE_ON_MONDAY,
                3: self.config.TRADE_ON_TUESDAY,
                4: self.config.TRADE_ON_WEDNESDAY,
                5: self.config.TRADE_ON_THURSDAY,
                6: self.config.TRADE_ON_FRIDAY,
                7: self.config.TRADE_ON_SATURDAY,
            }[dow_pine]
            if not allowed:
                return False

        # Month Filter
        if self.config.ENABLE_MONTH_FILTER:
            month = ts_gmt3.month
            allowed = {
                1: self.config.TRADE_IN_JANUARY,
                2: self.config.TRADE_IN_FEBRUARY,
                3: self.config.TRADE_IN_MARCH,
                4: self.config.TRADE_IN_APRIL,
                5: self.config.TRADE_IN_MAY,
                6: self.config.TRADE_IN_JUNE,
                7: self.config.TRADE_IN_JULY,
                8: self.config.TRADE_IN_AUGUST,
                9: self.config.TRADE_IN_SEPTEMBER,
                10: self.config.TRADE_IN_OCTOBER,
                11: self.config.TRADE_IN_NOVEMBER,
                12: self.config.TRADE_IN_DECEMBER,
            }[month]
            if not allowed:
                return False
                
        # Forbidden Hours
        if self.config.ENABLE_FORBIDDEN_HOURS:
            current_minutes = ts_gmt3.hour * 60 + ts_gmt3.minute
            start_minutes = self.config.FORBIDDEN_START_HOUR * 60 + self.config.FORBIDDEN_START_MINUTE
            end_minutes = self.config.FORBIDDEN_END_HOUR * 60 + self.config.FORBIDDEN_END_MINUTE

            if start_minutes <= end_minutes:
                if start_minutes <= current_minutes <= end_minutes:
                    return False
            else:
                # Spans midnight (e.g. 22:00 -> 06:00)
                if current_minutes >= start_minutes or current_minutes <= end_minutes:
                    return False

        return True
                    
    def calculate(self, candle, state: YulaState, index):
        high_p = candle["high"]
        low_p = candle["low"]

        # Entries are time-filtered in Pine, but exits must still run.
        time_allowed_for_entry = self._check_time_filters(candle)

        # 1) Momentum validation (may clear invalid momentum states)
        self._update_momentum(high_p, low_p, state)

        # 2) Touch range-break resets (Pine: resets touch tracking when invalidated)
        self._apply_range_break_logic(high_p, low_p, state)

        # 3) Trend break tracking (Pine: lastBreakIsSRangeHigh / lastBreakIsLRangeLow)
        self._update_break_tracking(high_p, low_p, state)

        # 4) Pending entry execution (two-step reversals)
        signal = self._execute_pending_entries_if_due(candle, state, index)

        # 5) Update ranges (touch detection)
        self._process_x_range(high_p, low_p, index, state)
        self._process_y_range(high_p, low_p, index, state)
        self._process_l_range(high_p, low_p, index, state)
        self._process_s_range(high_p, low_p, index, state)
        self._process_m_range(high_p, low_p, index, state)
        self._process_n_range(high_p, low_p, index, state)

        # 6) Update fibs (used mostly for visualization/diagnostics)
        self._update_fibs(state)

        # 7) Trade management (exits)
        self._check_exits(candle, state, index)

        # 8) Entry logic (time-filtered)
        if time_allowed_for_entry and signal is None:
            if self._should_open_long(state):
                signal = self._handle_long_entry(candle, state, index)

        if time_allowed_for_entry and signal is None:
            if self._should_open_short(state):
                signal = self._handle_short_entry(candle, state, index)

        # Pine: E resets C, F resets D
        if state.condition_E:
            state.condition_C = False
        if state.condition_F:
            state.condition_D = False

        return signal, state

    def _apply_range_break_logic(self, high, low, state):
        # Pine: Range break logic resets touch tracking when invalidated before confirmation.
        if state.x1LowPrice is not None and low < state.x1LowPrice and state.xongTouchCount < 3:
            state.xongTouchCount = 0
            state.latestXongPrices = [None] * 3
            state.latestXongBars = [None] * 3
            state.x2CandidatePrices = []
            state.x2CandidateBars = []
            state.x_fibs = {}
            if state.x_range_high is None and state.x_range_low is None:
                state.x1LowPrice = None
            if not state.x_range_active:
                state.condition_A = False
                state.condition_A1 = False

        if state.y1HighPrice is not None and high > state.y1HighPrice and state.yhortTouchCount < 3:
            state.yhortTouchCount = 0
            state.latestYhortPrices = [None] * 3
            state.latestYhortBars = [None] * 3
            state.y2CandidatePrices = []
            state.y2CandidateBars = []
            state.y_fibs = {}
            if state.y_range_high is None and state.y_range_low is None:
                state.y1HighPrice = None
            if not state.y_range_active:
                state.condition_B = False
                state.condition_B1 = False

        if state.l1LowPrice is not None and low < state.l1LowPrice and state.longTouchCount < 3:
            state.longTouchCount = 0
            state.latestLongPrices = [None] * 3
            state.latestLongBars = [None] * 3
            state.l2CandidatePrices = []
            state.l2CandidateBars = []
            state.l_fibs = {}
            if state.l_range_high is None and state.l_range_low is None:
                state.l1LowPrice = None

        if state.s1HighPrice is not None and high > state.s1HighPrice and state.shortTouchCount < 3:
            state.shortTouchCount = 0
            state.latestShortPrices = [None] * 3
            state.latestShortBars = [None] * 3
            state.s2CandidatePrices = []
            state.s2CandidateBars = []
            state.s_fibs = {}
            if state.s_range_high is None and state.s_range_low is None:
                state.s1HighPrice = None

        if state.m1LowPrice is not None and low < state.m1LowPrice and state.mongTouchCount < 3:
            state.mongTouchCount = 0
            state.latestMongPrices = [None] * 3
            state.latestMongBars = [None] * 3
            state.m2CandidatePrices = []
            state.m2CandidateBars = []
            state.m_fibs = {}
            if state.m_range_high is None and state.m_range_low is None:
                state.m1LowPrice = None

        if state.n1HighPrice is not None and high > state.n1HighPrice and state.nhortTouchCount < 3:
            state.nhortTouchCount = 0
            state.latestNhortPrices = [None] * 3
            state.latestNhortBars = [None] * 3
            state.n2CandidatePrices = []
            state.n2CandidateBars = []
            state.n_fibs = {}
            if state.n_range_high is None and state.n_range_low is None:
                state.n1HighPrice = None

    def _update_break_tracking(self, high, low, state):
        # Pine: trend detection based on L/S range breaks.
        if state.s_range_high is not None and high > state.s_range_high:
            state.lastBreakIsSRangeHigh = True
            state.lastBreakIsLRangeLow = False

        if state.l_range_low is not None and low < state.l_range_low:
            state.lastBreakIsLRangeLow = True
            state.lastBreakIsSRangeHigh = False

    def _execute_pending_entries_if_due(self, candle, state, index):
        if state.position_size != 0:
            return None

        if state.pendingLongEntry and state.pendingEntryBar is not None and index >= state.pendingEntryBar:
            state.pendingLongEntry = False
            state.pendingShortEntry = False
            state.pendingEntryBar = None
            state.pendingEntryReason = ""
            return self._open_position("LONG", candle, state, index, comment="Pending Long Entry")

        if state.pendingShortEntry and state.pendingEntryBar is not None and index >= state.pendingEntryBar:
            state.pendingShortEntry = False
            state.pendingLongEntry = False
            state.pendingEntryBar = None
            state.pendingEntryReason = ""
            return self._open_position("SHORT", candle, state, index, comment="Pending Short Entry")

        return None

    def _momentum_allowed(self, state):
        if not self.config.ENABLE_MOMENTUM_FILTER:
            return True, True

        if self.config.ENABLE_MOMENTUM_RANGE_BREAK_FILTER:
            is_long_allowed = (state.lastBreakIsSRangeHigh and state.momentumFavorsBullish) or (
                not state.lastBreakIsSRangeHigh and not state.lastBreakIsLRangeLow
            )
            is_short_allowed = (state.lastBreakIsLRangeLow and state.momentumFavorsBearish) or (
                not state.lastBreakIsSRangeHigh and not state.lastBreakIsLRangeLow
            )
            return is_long_allowed, is_short_allowed

        return state.momentumFavorsBullish, state.momentumFavorsBearish

    def _is_new_bullish_momentum_range(self, state) -> bool:
        return (
            (state.usedBullishMomentumBar is None or state.lastBullishMomentumBar is None or state.lastBullishMomentumBar != state.usedBullishMomentumBar)
            and state.m2FormedAfterL2
        )

    def _is_new_bearish_momentum_range(self, state) -> bool:
        return (
            (state.usedBearishMomentumBar is None or state.lastBearishMomentumBar is None or state.lastBearishMomentumBar != state.usedBearishMomentumBar)
            and state.n2FormedAfterS2
        )

    def _should_open_long(self, state) -> bool:
        is_long_allowed, _ = self._momentum_allowed(state)
        is_new_bullish = self._is_new_bullish_momentum_range(state)
        can_trade = not (state.position_size < 0 and state.trailingProfitSystemTriggered)
        return can_trade and is_long_allowed and is_new_bullish and state.condition_C

    def _should_open_short(self, state) -> bool:
        _, is_short_allowed = self._momentum_allowed(state)
        is_new_bearish = self._is_new_bearish_momentum_range(state)
        can_trade = not (state.position_size > 0 and state.trailingProfitSystemTriggered)
        return can_trade and is_short_allowed and is_new_bearish and state.condition_D

    def _close_all(self, candle, state, reason: str):
        if state.position_size == 0:
            return
        state.trades.append({
            "time": candle["timestamp"],
            "type": "EXIT_REV",
            "price": candle["close"],
            "size": abs(state.position_size),
            "comment": reason,
        })
        state.position_size = 0
        self._reset_position_state(state)

    def _open_position(self, direction: str, candle, state, index, comment: str):
        is_long = direction == "LONG"
        entry_price = candle["close"]

        state.position_size = 1 if is_long else -1
        state.entry_price = entry_price

        # Mark this momentum range as used (Pine: usedBullishMomentumBar := lastBullishMomentumBar, etc.)
        if is_long:
            state.usedBullishMomentumBar = state.lastBullishMomentumBar
        else:
            state.usedBearishMomentumBar = state.lastBearishMomentumBar

        state.trades.append({
            "time": candle["timestamp"],
            "type": "ENTRY_LONG" if is_long else "ENTRY_SHORT",
            "price": entry_price,
            "size": 1,
            "comment": comment,
        })

        # Setup TP system
        tp1, tp2 = self._calculate_tp_levels(entry_price, is_long)
        state.firstTPLevel = tp1
        state.secondTPLevel = tp2
        state.firstTPHit = False
        state.secondTPHit = False
        state.breakevenActive = False
        state.breakevenLevel = entry_price
        state.firstTPBar = None

        # Setup range trailing stop
        state.rangeTrailingStopActive = False
        state.rangeTrailingStopLevel = None
        state.highestPriceInPosition = candle["high"] if is_long else None
        state.lowestPriceInPosition = candle["low"] if not is_long else None
        state.activationLevel = self._calculate_activation_level(entry_price, is_long)

        # Setup trailing profit stop
        state.trailingProfitStopActive = False
        state.trailingProfitStopLevel = None
        state.trailingProfitSystemTriggered = False
        state.trailingProfitStopTier = 0

        return direction

    def _handle_long_entry(self, candle, state, index):
        if state.position_size > 0:
            return None

        if state.position_size < 0 and self.config.ENABLE_PENDING_ENTRY:
            self._close_all(candle, state, "Reverse to Long")
            state.pendingLongEntry = True
            state.pendingShortEntry = False
            state.pendingEntryBar = index + 1
            state.pendingEntryReason = "LONG SIGNAL (C+MOMENTUM+TIME)"
            return None

        if state.position_size < 0:
            self._close_all(candle, state, "Reverse to Long")

        if state.position_size == 0:
            return self._open_position("LONG", candle, state, index, comment="Long Entry")

        return None

    def _handle_short_entry(self, candle, state, index):
        if state.position_size < 0:
            return None

        if state.position_size > 0 and self.config.ENABLE_PENDING_ENTRY:
            self._close_all(candle, state, "Reverse to Short")
            state.pendingShortEntry = True
            state.pendingLongEntry = False
            state.pendingEntryBar = index + 1
            state.pendingEntryReason = "SHORT SIGNAL (D+MOMENTUM+TIME)"
            return None

        if state.position_size > 0:
            self._close_all(candle, state, "Reverse to Short")

        if state.position_size == 0:
            return self._open_position("SHORT", candle, state, index, comment="Short Entry")

        return None

    def _is_valid_height(self, current_price, candidates, is_long_range):
        """
        Checks if the current price is a valid candidate based on previous candidates.
        For Long Range (X, L, M): We look for Highs (X2, L2, M2). New candidate must be > all previous candidates.
        For Short Range (Y, S, N): We look for Lows (Y2, S2, N2). New candidate must be < all previous candidates.
        """
        if not candidates:
            return True
        
        for p in candidates:
            if is_long_range: # Looking for higher highs
                if current_price <= p:
                    return False
            else: # Looking for lower lows
                if current_price >= p:
                    return False
        return True

    def _get_compare_index(self, compare_with: str) -> int:
        return {"touch1": 0, "touch2": 1, "touch3": 2}.get(compare_with, 0)

    def _is_distance_valid(self, current_price, compare_with, prices, touch_index, required_distance_pct) -> bool:
        if compare_with == "none":
            return True

        compare_index = self._get_compare_index(compare_with)
        if compare_index >= touch_index:
            return False

        compare_price = prices[compare_index]
        if compare_price is None:
            return False

        return self._percent_diff(compare_price, current_price) >= required_distance_pct

    def _is_level_valid(self, current_price, compare_with, relation, prices, touch_index) -> bool:
        if compare_with == "none":
            return True

        compare_index = self._get_compare_index(compare_with)
        if compare_index >= touch_index:
            return False

        compare_price = prices[compare_index]
        if compare_price is None:
            return False

        if relation == "above":
            return current_price > compare_price
        return current_price < compare_price

    def _calculate_percent_difference(self, current, reference) -> float:
        if current is None or reference is None or reference == 0:
            return 0.0
        return abs(current - reference) / abs(reference) * 100

    def _is_within_tolerance(self, current_price, reference_level, tolerance_pct) -> bool:
        if current_price is None or reference_level is None or tolerance_pct is None:
            return False
        return self._calculate_percent_difference(current_price, reference_level) <= tolerance_pct

    def _process_x_range(self, high, low, index, state):
        # X Range (Long): Low (X1) -> High (X2) -> Retracement (X3)
        if state.latestXongBars[0] is not None and index - state.latestXongBars[0] > self.config.MAX_LINE_LENGTH:
            state.xongTouchCount = 0
            state.latestXongPrices = [None]*3
            state.latestXongBars = [None]*3
            state.x1LowPrice = None
            state.x2CandidatePrices = []
            state.x2CandidateBars = []
            state.x_fibs = {}
            state.x_range_active = False

        # Touch 1 (Low)
        if state.xongTouchCount == 0:
            current_price = high if self.config.X1_BAND == "upper" else low
            state.x1LowPrice = low  # Pine: x1LowPrice := low (for range-break resets)
            state.latestXongPrices[0] = current_price
            state.latestXongBars[0] = index
            state.xongTouchCount = 1
                
        # Touch 2 (High) Candidate & Confirmation
        elif state.xongTouchCount == 1:
            current_price = high if self.config.X2_BAND == "upper" else low

            # Update Candidate High
            dist_ok = self._is_distance_valid(
                current_price,
                self.config.X2_COMPARE_WITH,
                state.latestXongPrices,
                touch_index=1,
                required_distance_pct=self.config.X2_MIN_DIST_PCT,
            )
            level_ok = self._is_level_valid(
                current_price,
                self.config.X2_COMPARE_WITH,
                self.config.X2_SHOULD_BE,
                state.latestXongPrices,
                touch_index=1,
            )
            
            # Check if valid height (Higher than previous candidates)
            height_ok = self._is_valid_height(current_price, state.x2CandidatePrices, is_long_range=True)
            
            if dist_ok and level_ok and height_ok:
                state.x2CandidatePrices.append(current_price)
                state.x2CandidateBars.append(index)
                # print(f"DEBUG: Added X2 Candidate at {index}, Price: {high}")
            
            # Check Confirmation (Retracement)
            confirmed_x2 = None
            confirmed_x2_bar = None
            x3_price = None
            
            # Iterate candidates to see if any is confirmed by current Low
            for i in range(len(state.x2CandidatePrices) - 1, -1, -1):
                cand_p = state.x2CandidatePrices[i]
                cand_b = state.x2CandidateBars[i]
                
                # Threshold check: Price drops by X3_MIN_DIST_BELOW_X2_PCT
                drop_pct = 0
                if cand_p > 0:
                    drop_pct = (cand_p - low) / cand_p * 100
                
                bars_between = index - cand_b - 1
                if low < cand_p and drop_pct >= self.config.X3_MIN_DIST_BELOW_X2_PCT and bars_between >= self.config.MIN_BARS_BETWEEN_TOUCH_2_3_XY:
                    confirmed_x2 = cand_p
                    confirmed_x2_bar = cand_b
                    x3_price = low
                    break # Found the first valid confirmation? Pine loop breaks on first match.
            
            if confirmed_x2:
                state.latestXongPrices[1] = confirmed_x2
                state.latestXongBars[1] = confirmed_x2_bar
                state.latestXongPrices[2] = x3_price
                state.latestXongBars[2] = index
                
                state.prev_x_range_high = state.x_range_high
                state.x_range_low = state.latestXongPrices[0] # X1 (Low)
                state.x_range_high = confirmed_x2 # X2 (High)
                state.x_range_active = True
                
                if state.prev_x_range_high and state.x_range_high > state.prev_x_range_high:
                    state.condition_B = False
                    state.condition_B1 = False
                    state.condition_A = True
                
                # Reset
                state.xongTouchCount = 0
                state.latestXongPrices = [None]*3
                state.latestXongBars = [None]*3
                state.x1LowPrice = None
                state.x2CandidatePrices = []
                state.x2CandidateBars = []

    def _process_y_range(self, high, low, index, state):
        # Y Range (Short): High (Y1) -> Low (Y2) -> Retracement Up (Y3)
        if state.latestYhortBars[0] is not None and index - state.latestYhortBars[0] > self.config.MAX_LINE_LENGTH:
            state.yhortTouchCount = 0
            state.latestYhortPrices = [None]*3
            state.latestYhortBars = [None]*3
            state.y1HighPrice = None
            state.y2CandidatePrices = []
            state.y2CandidateBars = []
            state.y_fibs = {}
            state.y_range_active = False

        if state.yhortTouchCount == 0:
            current_price = high if self.config.Y1_BAND == "upper" else low
            state.y1HighPrice = high  # Pine: y1HighPrice := high (for range-break resets)
            state.latestYhortPrices[0] = current_price
            state.latestYhortBars[0] = index
            state.yhortTouchCount = 1
            
        elif state.yhortTouchCount == 1:
            current_price = high if self.config.Y2_BAND == "upper" else low

            # Update Candidate Low
            dist_ok = self._is_distance_valid(
                current_price,
                self.config.Y2_COMPARE_WITH,
                state.latestYhortPrices,
                touch_index=1,
                required_distance_pct=self.config.Y2_MIN_DIST_PCT,
            )
            level_ok = self._is_level_valid(
                current_price,
                self.config.Y2_COMPARE_WITH,
                self.config.Y2_SHOULD_BE,
                state.latestYhortPrices,
                touch_index=1,
            )
            
            # Check if valid height (Lower than previous candidates)
            height_ok = self._is_valid_height(current_price, state.y2CandidatePrices, is_long_range=False)
            
            if dist_ok and level_ok and height_ok:
                state.y2CandidatePrices.append(current_price)
                state.y2CandidateBars.append(index)
            
            # Check Confirmation (Retracement Up)
            confirmed_y2 = None
            confirmed_y2_bar = None
            y3_price = None
            
            for i in range(len(state.y2CandidatePrices) - 1, -1, -1):
                cand_p = state.y2CandidatePrices[i]
                cand_b = state.y2CandidateBars[i]
                
                # Threshold: Price rises by Y3_MIN_DIST_ABOVE_Y2_PCT
                rise_pct = 0
                if cand_p > 0:
                    rise_pct = (high - cand_p) / cand_p * 100

                bars_between = index - cand_b - 1
                if high > cand_p and rise_pct >= self.config.Y3_MIN_DIST_ABOVE_Y2_PCT and bars_between >= self.config.MIN_BARS_BETWEEN_TOUCH_2_3_XY:
                    confirmed_y2 = cand_p
                    confirmed_y2_bar = cand_b
                    y3_price = high
                    break
            
            if confirmed_y2:
                state.latestYhortPrices[1] = confirmed_y2
                state.latestYhortBars[1] = confirmed_y2_bar
                state.latestYhortPrices[2] = y3_price
                state.latestYhortBars[2] = index
                
                state.prev_y_range_low = state.y_range_low
                state.y_range_high = state.latestYhortPrices[0] # Y1 (High)
                state.y_range_low = confirmed_y2 # Y2 (Low)
                state.y_range_active = True
                
                if state.prev_y_range_low and state.y_range_low < state.prev_y_range_low:
                    state.condition_A = False
                    state.condition_A1 = False
                    state.condition_B = True
                
                state.yhortTouchCount = 0
                state.latestYhortPrices = [None]*3
                state.latestYhortBars = [None]*3
                state.y1HighPrice = None
                state.y2CandidatePrices = []
                state.y2CandidateBars = []

    def _process_l_range(self, high, low, index, state):
        # L Range (Long): Low -> High -> Retracement
        if state.latestLongBars[0] is not None and index - state.latestLongBars[0] > self.config.MAX_LINE_LENGTH:
            state.longTouchCount = 0
            state.latestLongPrices = [None]*3
            state.latestLongBars = [None]*3
            state.l1LowPrice = None
            state.l2CandidatePrices = []
            state.l2CandidateBars = []

        if state.longTouchCount == 0:
            current_price = high if self.config.L1_BAND == "upper" else low
            state.l1LowPrice = low  # Pine: l1LowPrice := low (for range-break resets)
            state.latestLongPrices[0] = current_price
            state.latestLongBars[0] = index
            state.longTouchCount = 1
            state.lastL1BarIndex = index

        elif state.longTouchCount == 1:
            current_price = high if self.config.L2_BAND == "upper" else low

            dist_ok = self._is_distance_valid(
                current_price,
                self.config.L2_COMPARE_WITH,
                state.latestLongPrices,
                touch_index=1,
                required_distance_pct=self.config.L2_MIN_DIST_PCT,
            )
            level_ok = self._is_level_valid(
                current_price,
                self.config.L2_COMPARE_WITH,
                self.config.L2_SHOULD_BE,
                state.latestLongPrices,
                touch_index=1,
            )
            
            # Check valid height (Higher Highs)
            height_ok = self._is_valid_height(current_price, state.l2CandidatePrices, is_long_range=True)
            
            if dist_ok and level_ok and height_ok:
                state.l2CandidatePrices.append(current_price)
                state.l2CandidateBars.append(index)

            confirmed_l2 = None
            confirmed_l2_bar = None
            l3_price = None
            
            for i in range(len(state.l2CandidatePrices) - 1, -1, -1):
                cand_p = state.l2CandidatePrices[i]
                cand_b = state.l2CandidateBars[i]
                
                drop_pct = 0
                if cand_p > 0:
                    drop_pct = (cand_p - low) / cand_p * 100
                    
                bars_between = index - cand_b - 1
                if low < cand_p and drop_pct >= self.config.L3_MIN_DIST_BELOW_L2_PCT and bars_between >= self.config.MIN_BARS_BETWEEN_TOUCH_2_3_LS:
                    confirmed_l2 = cand_p
                    confirmed_l2_bar = cand_b
                    l3_price = low
                    break
            
            if confirmed_l2:
                state.latestLongPrices[1] = confirmed_l2
                state.latestLongBars[1] = confirmed_l2_bar
                state.latestLongPrices[2] = l3_price
                state.latestLongBars[2] = index
                
                state.lastL2BarIndex = confirmed_l2_bar
                state.lastL2FormationBar = confirmed_l2_bar
                state.m2FormedAfterL2 = False  # Reset flag
                
                state.prev_l_range_high = state.l_range_high
                state.prev_l_range_low = state.l_range_low
                
                # MOMENTUM CALCULATION
                if state.lastL1BarIndex is not None and state.lastL2BarIndex is not None:
                    state.bullishMomentum = abs(state.lastL2BarIndex - state.lastL1BarIndex)
                    state.bullishMomentumStartBar = min(state.lastL1BarIndex, state.lastL2BarIndex)
                    state.bullishMomentumEndBar = max(state.lastL1BarIndex, state.lastL2BarIndex)
                
                state.validL2BarIndex = confirmed_l2_bar
                state.lastBullishMomentumBar = index # Using current bar as the timestamp of this momentum event
                
                state.l_range_low = state.latestLongPrices[0]
                state.l_range_high = confirmed_l2

                # Update active momentum levels after range is set
                state.activeBullishMomentumLRangeHigh = state.l_range_high
                state.activeBullishMomentumLRangeLow = state.l_range_low
                
                if state.prev_l_range_low:
                    is_lower = False
                    if self.config.ENABLE_CD_THRESHOLD:
                        threshold = state.prev_l_range_low * (1 - self.config.CD_THRESHOLD_PERCENT / 100)
                        is_lower = state.l_range_low < threshold
                    else:
                        is_lower = state.l_range_low < state.prev_l_range_low
                    
                    if is_lower:
                        state.condition_D = True
                
                if state.prev_l_range_high:
                    is_higher = False
                    if self.config.ENABLE_CD_THRESHOLD:
                         threshold = state.prev_l_range_high * (1 + self.config.CD_THRESHOLD_PERCENT / 100)
                         is_higher = state.l_range_high > threshold
                    else:
                         is_higher = state.l_range_high > state.prev_l_range_high
                    
                    if is_higher:
                        state.condition_F = True
                        state.condition_D = False
                
                state.longTouchCount = 0
                state.latestLongPrices = [None]*3
                state.latestLongBars = [None]*3
                state.l1LowPrice = None
                state.l2CandidatePrices = []
                state.l2CandidateBars = []

    def _process_s_range(self, high, low, index, state):
        # S Range (Short): High -> Low -> Retracement
        if state.latestShortBars[0] is not None and index - state.latestShortBars[0] > self.config.MAX_LINE_LENGTH:
            state.shortTouchCount = 0
            state.latestShortPrices = [None]*3
            state.latestShortBars = [None]*3
            state.s1HighPrice = None
            state.s2CandidatePrices = []
            state.s2CandidateBars = []

        if state.shortTouchCount == 0:
            current_price = high if self.config.S1_BAND == "upper" else low
            state.s1HighPrice = high  # Pine: s1HighPrice := high (for range-break resets)
            state.latestShortPrices[0] = current_price
            state.latestShortBars[0] = index
            state.shortTouchCount = 1
            state.lastS1BarIndex = index

        elif state.shortTouchCount == 1:
            current_price = high if self.config.S2_BAND == "upper" else low

            dist_ok = self._is_distance_valid(
                current_price,
                self.config.S2_COMPARE_WITH,
                state.latestShortPrices,
                touch_index=1,
                required_distance_pct=self.config.S2_MIN_DIST_PCT,
            )
            level_ok = self._is_level_valid(
                current_price,
                self.config.S2_COMPARE_WITH,
                self.config.S2_SHOULD_BE,
                state.latestShortPrices,
                touch_index=1,
            )
            
            # Check valid height (Lower Lows)
            height_ok = self._is_valid_height(current_price, state.s2CandidatePrices, is_long_range=False)
            
            if dist_ok and level_ok and height_ok:
                state.s2CandidatePrices.append(current_price)
                state.s2CandidateBars.append(index)

            confirmed_s2 = None
            confirmed_s2_bar = None
            s3_price = None
            
            for i in range(len(state.s2CandidatePrices) - 1, -1, -1):
                cand_p = state.s2CandidatePrices[i]
                cand_b = state.s2CandidateBars[i]
                
                rise_pct = 0
                if cand_p > 0:
                    rise_pct = (high - cand_p) / cand_p * 100
                    
                bars_between = index - cand_b - 1
                if high > cand_p and rise_pct >= self.config.S3_MIN_DIST_ABOVE_S2_PCT and bars_between >= self.config.MIN_BARS_BETWEEN_TOUCH_2_3_LS:
                    confirmed_s2 = cand_p
                    confirmed_s2_bar = cand_b
                    s3_price = high
                    break
            
            if confirmed_s2:
                state.latestShortPrices[1] = confirmed_s2
                state.latestShortBars[1] = confirmed_s2_bar
                state.latestShortPrices[2] = s3_price
                state.latestShortBars[2] = index
                
                state.lastS2BarIndex = confirmed_s2_bar
                state.lastS2FormationBar = confirmed_s2_bar
                state.n2FormedAfterS2 = False  # Reset flag
                
                state.prev_s_range_high = state.s_range_high
                state.prev_s_range_low = state.s_range_low
                
                # MOMENTUM CALCULATION
                if state.lastS1BarIndex is not None and state.lastS2BarIndex is not None:
                    state.bearishMomentum = abs(state.lastS2BarIndex - state.lastS1BarIndex)
                    state.bearishMomentumStartBar = min(state.lastS1BarIndex, state.lastS2BarIndex)
                    state.bearishMomentumEndBar = max(state.lastS1BarIndex, state.lastS2BarIndex)
                
                state.validS2BarIndex = confirmed_s2_bar
                state.lastBearishMomentumBar = index
                
                state.s_range_high = state.latestShortPrices[0]
                state.s_range_low = confirmed_s2

                # Update active momentum levels after range is set
                state.activeBearishMomentumSRangeHigh = state.s_range_high
                state.activeBearishMomentumSRangeLow = state.s_range_low
                
                if state.prev_s_range_high:
                    is_higher = False
                    if self.config.ENABLE_CD_THRESHOLD:
                        threshold = state.prev_s_range_high * (1 + self.config.CD_THRESHOLD_PERCENT / 100)
                        is_higher = state.s_range_high > threshold
                    else:
                        is_higher = state.s_range_high > state.prev_s_range_high
                    
                    if is_higher:
                        state.condition_C = True
                
                if state.prev_s_range_low:
                    is_lower = False
                    if self.config.ENABLE_CD_THRESHOLD:
                        threshold = state.prev_s_range_low * (1 - self.config.CD_THRESHOLD_PERCENT / 100)
                        is_lower = state.s_range_low < threshold
                    else:
                        is_lower = state.s_range_low < state.prev_s_range_low
                    
                    if is_lower:
                        state.condition_E = True
                        state.condition_C = False
                
                state.shortTouchCount = 0
                state.latestShortPrices = [None]*3
                state.latestShortBars = [None]*3
                state.s1HighPrice = None
                state.s2CandidatePrices = []
                state.s2CandidateBars = []

    def _process_m_range(self, high, low, index, state):
        # M Range (Long): Low -> High -> Retracement
        if state.latestMongBars[0] is not None and index - state.latestMongBars[0] > self.config.MAX_LINE_LENGTH:
            state.mongTouchCount = 0
            state.latestMongPrices = [None]*3
            state.latestMongBars = [None]*3
            state.m1LowPrice = None
            state.m2CandidatePrices = []
            state.m2CandidateBars = []
            state.m_range_active = False

        if state.mongTouchCount == 0:
            current_price = high if self.config.M1_BAND == "upper" else low
            state.m1LowPrice = low  # Pine: m1LowPrice := low (for range-break resets)
            state.latestMongPrices[0] = current_price
            state.latestMongBars[0] = index
            state.mongTouchCount = 1

        elif state.mongTouchCount == 1:
            current_price = high if self.config.M2_BAND == "upper" else low

            dist_ok = self._is_distance_valid(
                current_price,
                self.config.M2_COMPARE_WITH,
                state.latestMongPrices,
                touch_index=1,
                required_distance_pct=self.config.M2_MIN_DIST_PCT,
            )
            level_ok = self._is_level_valid(
                current_price,
                self.config.M2_COMPARE_WITH,
                self.config.M2_SHOULD_BE,
                state.latestMongPrices,
                touch_index=1,
            )
            
            # Check valid height (Higher Highs)
            height_ok = self._is_valid_height(current_price, state.m2CandidatePrices, is_long_range=True)
            
            if dist_ok and level_ok and height_ok:
                state.m2CandidatePrices.append(current_price)
                state.m2CandidateBars.append(index)

            confirmed_m2 = None
            confirmed_m2_bar = None
            m3_price = None
            
            for i in range(len(state.m2CandidatePrices) - 1, -1, -1):
                cand_p = state.m2CandidatePrices[i]
                cand_b = state.m2CandidateBars[i]
                
                drop_pct = 0
                if cand_p > 0:
                    drop_pct = (cand_p - low) / cand_p * 100
                    
                bars_between = index - cand_b - 1
                if low < cand_p and drop_pct >= self.config.M3_MIN_DIST_BELOW_M2_PCT and bars_between >= self.config.MIN_BARS_BETWEEN_TOUCH_2_3_MN:
                    confirmed_m2 = cand_p
                    confirmed_m2_bar = cand_b
                    m3_price = low
                    break
            
            if confirmed_m2:
                state.latestMongPrices[1] = confirmed_m2
                state.latestMongBars[1] = confirmed_m2_bar
                state.latestMongPrices[2] = m3_price
                state.latestMongBars[2] = index
                
                state.validM2BarIndex = confirmed_m2_bar
                
                if state.lastL2FormationBar is not None and confirmed_m2_bar > state.lastL2FormationBar:
                    state.m2FormedAfterL2 = True
                    
                # Momentum Logic for M
                if state.validL2BarIndex is not None and state.validL2BarIndex < confirmed_m2_bar:
                    state.bullishFibMomentum = abs(confirmed_m2_bar - state.validL2BarIndex)
                    if state.bullishMomentum is not None and state.bullishFibMomentum is not None and self._is_bullish_momentum_valid(high, low, state):
                        if state.bullishMomentum < (state.bullishFibMomentum / self.config.MOMENTUM_MULTIPLIER):
                            state.momentumFavorsBullish = True
                        else:
                            state.momentumFavorsBullish = False

                state.m_range_low = state.latestMongPrices[0]
                state.m_range_high = confirmed_m2
                state.m_range_active = True
                
                state.mongTouchCount = 0
                state.latestMongPrices = [None]*3
                state.latestMongBars = [None]*3
                state.m1LowPrice = None
                state.m2CandidatePrices = []
                state.m2CandidateBars = []

    def _process_n_range(self, high, low, index, state):
        # N Range (Short): High -> Low -> Retracement
        if state.latestNhortBars[0] is not None and index - state.latestNhortBars[0] > self.config.MAX_LINE_LENGTH:
            state.nhortTouchCount = 0
            state.latestNhortPrices = [None]*3
            state.latestNhortBars = [None]*3
            state.n1HighPrice = None
            state.n2CandidatePrices = []
            state.n2CandidateBars = []
            state.n_range_active = False

        if state.nhortTouchCount == 0:
            current_price = high if self.config.N1_BAND == "upper" else low
            state.n1HighPrice = high  # Pine: n1HighPrice := high (for range-break resets)
            state.latestNhortPrices[0] = current_price
            state.latestNhortBars[0] = index
            state.nhortTouchCount = 1

        elif state.nhortTouchCount == 1:
            current_price = high if self.config.N2_BAND == "upper" else low

            dist_ok = self._is_distance_valid(
                current_price,
                self.config.N2_COMPARE_WITH,
                state.latestNhortPrices,
                touch_index=1,
                required_distance_pct=self.config.N2_MIN_DIST_PCT,
            )
            level_ok = self._is_level_valid(
                current_price,
                self.config.N2_COMPARE_WITH,
                self.config.N2_SHOULD_BE,
                state.latestNhortPrices,
                touch_index=1,
            )
            
            # Check valid height (Lower Lows)
            height_ok = self._is_valid_height(current_price, state.n2CandidatePrices, is_long_range=False)
            
            if dist_ok and level_ok and height_ok:
                state.n2CandidatePrices.append(current_price)
                state.n2CandidateBars.append(index)

            confirmed_n2 = None
            confirmed_n2_bar = None
            n3_price = None
            
            for i in range(len(state.n2CandidatePrices) - 1, -1, -1):
                cand_p = state.n2CandidatePrices[i]
                cand_b = state.n2CandidateBars[i]
                
                rise_pct = 0
                if cand_p > 0:
                    rise_pct = (high - cand_p) / cand_p * 100
                    
                bars_between = index - cand_b - 1
                if high > cand_p and rise_pct >= self.config.N3_MIN_DIST_ABOVE_N2_PCT and bars_between >= self.config.MIN_BARS_BETWEEN_TOUCH_2_3_MN:
                    confirmed_n2 = cand_p
                    confirmed_n2_bar = cand_b
                    n3_price = high
                    break
            
            if confirmed_n2:
                state.latestNhortPrices[1] = confirmed_n2
                state.latestNhortBars[1] = confirmed_n2_bar
                state.latestNhortPrices[2] = n3_price
                state.latestNhortBars[2] = index
                
                state.validN2BarIndex = confirmed_n2_bar

                if state.lastS2FormationBar is not None and confirmed_n2_bar > state.lastS2FormationBar:
                    state.n2FormedAfterS2 = True
                
                # Momentum Logic for N
                if state.validS2BarIndex is not None and state.validS2BarIndex < confirmed_n2_bar:
                    state.bearishFibMomentum = abs(confirmed_n2_bar - state.validS2BarIndex)
                    if state.bearishMomentum is not None and state.bearishFibMomentum is not None and self._is_bearish_momentum_valid(high, low, state):
                        if state.bearishMomentum < (state.bearishFibMomentum / self.config.MOMENTUM_MULTIPLIER):
                            state.momentumFavorsBearish = True
                        else:
                            state.momentumFavorsBearish = False

                state.n_range_high = state.latestNhortPrices[0]
                state.n_range_low = confirmed_n2
                state.n_range_active = True
                
                state.nhortTouchCount = 0
                state.latestNhortPrices = [None]*3
                state.latestNhortBars = [None]*3
                state.n1HighPrice = None
                state.n2CandidatePrices = []
                state.n2CandidateBars = []

    def _update_fibs(self, state):
        # X Fibs (Long Entry)
        if state.x_range_active and state.x_range_high is not None and state.x_range_low is not None:
            # X1 (Low) to X2 (High)
            upper = state.x_range_high # X2
            lower = state.x_range_low # X1
            dist = upper - lower
            
            state.x_fibs[self.config.FIB_382] = upper - (dist * self.config.FIB_382)
            state.x_fibs[self.config.FIB_500] = upper - (dist * self.config.FIB_500)
            state.x_fibs[self.config.FIB_618] = upper - (dist * self.config.FIB_618)
            state.x_fibs[self.config.FIB_705] = upper - (dist * self.config.FIB_705)

        # Y Fibs (Short Entry)
        if state.y_range_active and state.y_range_high is not None and state.y_range_low is not None:
            # Y1 (High) to Y2 (Low)
            lower = state.y_range_low # Y2
            upper = state.y_range_high # Y1
            dist = upper - lower
            
            state.y_fibs[self.config.FIB_382] = lower + (dist * self.config.FIB_382)
            state.y_fibs[self.config.FIB_500] = lower + (dist * self.config.FIB_500)
            state.y_fibs[self.config.FIB_618] = lower + (dist * self.config.FIB_618)
            state.y_fibs[self.config.FIB_705] = lower + (dist * self.config.FIB_705)

    def _is_bullish_momentum_valid(self, high, low, state) -> bool:
        is_valid = (
            state.bullishMomentum is not None
            and state.activeBullishMomentumLRangeHigh is not None
            and state.activeBullishMomentumLRangeLow is not None
        )
        if not is_valid:
            return False

        if self.config.ENABLE_MOMENTUM_TOLERANCE:
            high_diff = self._calculate_percent_difference(state.l_range_high, state.activeBullishMomentumLRangeHigh)
            low_diff = self._calculate_percent_difference(state.l_range_low, state.activeBullishMomentumLRangeLow)

            if high_diff > self.config.MOMENTUM_TOLERANCE_PERCENT or low_diff > self.config.MOMENTUM_TOLERANCE_PERCENT:
                return False

            low_break_valid = low >= state.activeBullishMomentumLRangeLow or self._is_within_tolerance(
                low, state.activeBullishMomentumLRangeLow, self.config.MOMENTUM_TOLERANCE_PERCENT
            )
            high_break_valid = high <= state.activeBullishMomentumLRangeHigh or self._is_within_tolerance(
                high, state.activeBullishMomentumLRangeHigh, self.config.MOMENTUM_TOLERANCE_PERCENT
            )

            return low_break_valid and high_break_valid

        # Strict mode
        if state.l_range_high != state.activeBullishMomentumLRangeHigh or state.l_range_low != state.activeBullishMomentumLRangeLow:
            return False

        return not (low < state.activeBullishMomentumLRangeLow or high > state.activeBullishMomentumLRangeHigh)

    def _is_bearish_momentum_valid(self, high, low, state) -> bool:
        is_valid = (
            state.bearishMomentum is not None
            and state.activeBearishMomentumSRangeHigh is not None
            and state.activeBearishMomentumSRangeLow is not None
        )
        if not is_valid:
            return False

        if self.config.ENABLE_MOMENTUM_TOLERANCE:
            high_diff = self._calculate_percent_difference(state.s_range_high, state.activeBearishMomentumSRangeHigh)
            low_diff = self._calculate_percent_difference(state.s_range_low, state.activeBearishMomentumSRangeLow)

            if high_diff > self.config.MOMENTUM_TOLERANCE_PERCENT or low_diff > self.config.MOMENTUM_TOLERANCE_PERCENT:
                return False

            high_break_valid = high <= state.activeBearishMomentumSRangeHigh or self._is_within_tolerance(
                high, state.activeBearishMomentumSRangeHigh, self.config.MOMENTUM_TOLERANCE_PERCENT
            )
            low_break_valid = low >= state.activeBearishMomentumSRangeLow or self._is_within_tolerance(
                low, state.activeBearishMomentumSRangeLow, self.config.MOMENTUM_TOLERANCE_PERCENT
            )

            return high_break_valid and low_break_valid

        # Strict mode
        if state.s_range_high != state.activeBearishMomentumSRangeHigh or state.s_range_low != state.activeBearishMomentumSRangeLow:
            return False

        return not (high > state.activeBearishMomentumSRangeHigh or low < state.activeBearishMomentumSRangeLow)

    def _update_momentum(self, high, low, state):
        bullish_valid = self._is_bullish_momentum_valid(high, low, state)
        bearish_valid = self._is_bearish_momentum_valid(high, low, state)

        if not bullish_valid and state.bullishMomentum is not None:
            state.bullishMomentum = None
            state.activeBullishMomentumLRangeHigh = None
            state.activeBullishMomentumLRangeLow = None
            state.bullishMomentumStartBar = None
            state.bullishMomentumEndBar = None
            state.momentumFavorsBullish = False
            if state.bullishFibMomentum is not None:
                state.bullishFibMomentum = None
                state.bullishFibMomentumStartBar = None
                state.bullishFibMomentumEndBar = None

        if not bearish_valid and state.bearishMomentum is not None:
            state.bearishMomentum = None
            state.activeBearishMomentumSRangeHigh = None
            state.activeBearishMomentumSRangeLow = None
            state.bearishMomentumStartBar = None
            state.bearishMomentumEndBar = None
            state.momentumFavorsBearish = False
            if state.bearishFibMomentum is not None:
                state.bearishFibMomentum = None
                state.bearishFibMomentumStartBar = None
                state.bearishFibMomentumEndBar = None

    def _get_current_loss_percent(self, is_long: bool, entry_price: float, close_price: float) -> Optional[float]:
        if entry_price is None:
            return None
        if is_long:
            return (entry_price - close_price) / entry_price * 100
        return (close_price - entry_price) / entry_price * 100

    def _get_trailing_profit_tier_to_activate(self, is_long: bool, entry_price: float, close_price: float) -> int:
        if not self.config.ENABLE_TRAILING_PROFIT_STOP or entry_price is None:
            return 0

        loss = self._get_current_loss_percent(is_long, entry_price, close_price)
        if loss is None:
            return 0

        if loss >= self.config.TRAILING_PROFIT_LOSS_THRESHOLD_3:
            return 3
        if loss >= self.config.TRAILING_PROFIT_LOSS_THRESHOLD_2:
            return 2
        if loss >= self.config.TRAILING_PROFIT_LOSS_THRESHOLD_1:
            return 1
        return 0

    def _calculate_trailing_profit_stop_level_for_tier(self, tier: int, is_long: bool, entry_price: float) -> Optional[float]:
        if entry_price is None or tier <= 0:
            return None

        take = (
            self.config.TRAILING_PROFIT_TAKE_LEVEL_1
            if tier == 1
            else (self.config.TRAILING_PROFIT_TAKE_LEVEL_2 if tier == 2 else self.config.TRAILING_PROFIT_TAKE_LEVEL_3)
        )
        if is_long:
            return entry_price * (1 - take / 100)
        return entry_price * (1 + take / 100)

    def _is_trailing_profit_stop_hit(self, is_long: bool, close_price: float, stop_level: Optional[float]) -> bool:
        if not self.config.ENABLE_TRAILING_PROFIT_STOP or stop_level is None:
            return False
        if is_long:
            return close_price >= stop_level
        return close_price <= stop_level

    def _is_max_loss_hit(self, is_long: bool, entry_price: float, close_price: float) -> bool:
        if entry_price is None or not self.config.ENABLE_MAX_LOSS_PROTECTION or self.config.MAX_LOSS_PERCENTAGE <= 0:
            return False
        threshold = self.config.MAX_LOSS_PERCENTAGE / 100
        if is_long:
            return close_price <= entry_price * (1 - threshold)
        return close_price >= entry_price * (1 + threshold)

    def _check_exits(self, candle, state, index):
        if state.position_size == 0 or state.entry_price is None:
            return

        high = candle["high"]
        low = candle["low"]
        close = candle["close"]
        timestamp = candle["timestamp"]
        
        is_long = state.position_size > 0
        
        # --- MAX LOSS CHECK (PRIORITY) ---
        if self.config.ENABLE_MAX_LOSS_PROTECTION and self.config.MAX_LOSS_PERCENTAGE > 0:
            # Check against Low (Long) or High (Short) for intra-bar stop
            check_price = low if is_long else high
            if self._is_max_loss_hit(is_long, state.entry_price, check_price):
                loss_price = (
                    state.entry_price * (1 - self.config.MAX_LOSS_PERCENTAGE / 100)
                    if is_long
                    else state.entry_price * (1 + self.config.MAX_LOSS_PERCENTAGE / 100)
                )
                state.trades.append({
                    "time": timestamp,
                    "type": "EXIT_SL",
                    "price": loss_price,
                    "size": abs(state.position_size),
                    "comment": "Max Loss Hit",
                })
                state.position_size = 0
                self._reset_position_state(state)
                return
        
        # Update Highest/Lowest for Trailing
        if is_long:
            if state.highestPriceInPosition is None or high > state.highestPriceInPosition:
                state.highestPriceInPosition = high
        else:
            if state.lowestPriceInPosition is None or low < state.lowestPriceInPosition:
                state.lowestPriceInPosition = low

        # --- ADVANCED TP SYSTEM ---
        if self.config.ENABLE_ADVANCED_TP and state.firstTPLevel is not None:
            # First TP
            if not state.firstTPHit:
                tp_hit = False
                if is_long and high >= state.firstTPLevel:
                    tp_hit = True
                elif not is_long and low <= state.firstTPLevel:
                    tp_hit = True
                
                if tp_hit:
                    # Close partial
                    qty = abs(state.position_size) * self.config.FIRST_TP_QUANTITY / 100
                    state.position_size -= qty if is_long else -qty
                    state.firstTPHit = True
                    state.firstTPBar = index
                    state.trades.append({
                        "time": timestamp,
                        "type": "EXIT_TP1",
                        "price": state.firstTPLevel,
                        "size": qty,
                        "comment": "First TP Hit",
                    })
                    
                    if self.config.ENABLE_BREAKEVEN_AFTER_FIRST_TP:
                        state.breakevenActive = True
                        state.breakevenLevel = state.entry_price

            # Second TP
            if not state.secondTPHit and state.secondTPLevel is not None:
                tp_hit = False
                if is_long and high >= state.secondTPLevel:
                    tp_hit = True
                elif not is_long and low <= state.secondTPLevel:
                    tp_hit = True
                
                if tp_hit:
                    # Close All
                    state.trades.append({
                        "time": timestamp,
                        "type": "EXIT_TP2",
                        "price": state.secondTPLevel,
                        "size": abs(state.position_size),
                        "comment": "Second TP Hit",
                    })
                    state.position_size = 0
                    state.secondTPHit = True
                    self._reset_position_state(state)
                    return

            # Breakeven
            if state.firstTPHit and state.breakevenActive and not state.secondTPHit:
                # Pine: wait at least 1 full bar after TP1.
                if state.firstTPBar is None or index > state.firstTPBar + 1:
                    be_hit = False
                    if is_long and low <= state.breakevenLevel:
                        be_hit = True
                    elif not is_long and high >= state.breakevenLevel:
                        be_hit = True

                    if be_hit:
                        state.trades.append({
                            "time": timestamp,
                            "type": "EXIT_BE",
                            "price": state.breakevenLevel,
                            "size": abs(state.position_size),
                            "comment": "Breakeven Hit",
                        })
                        state.position_size = 0
                        self._reset_position_state(state)
                        return

        # --- TRAILING PROFIT STOP (3-TIER, LOSS-BASED) ---
        if self.config.ENABLE_TRAILING_PROFIT_STOP and not state.trailingProfitSystemTriggered and (
            not self.config.ENABLE_ADVANCED_TP or not state.firstTPHit
        ):
            tier_to_activate = self._get_trailing_profit_tier_to_activate(is_long, state.entry_price, close)
            if tier_to_activate > 0:
                state.trailingProfitSystemTriggered = True
                state.trailingProfitStopActive = True
                state.trailingProfitStopTier = tier_to_activate
                state.trailingProfitStopLevel = self._calculate_trailing_profit_stop_level_for_tier(
                    tier_to_activate, is_long, state.entry_price
                )

        if state.trailingProfitStopActive:
            new_tier = self._get_trailing_profit_tier_to_activate(is_long, state.entry_price, close)
            if new_tier > state.trailingProfitStopTier:
                state.trailingProfitStopTier = new_tier
                state.trailingProfitStopLevel = self._calculate_trailing_profit_stop_level_for_tier(
                    new_tier, is_long, state.entry_price
                )

            if self._is_trailing_profit_stop_hit(is_long, close, state.trailingProfitStopLevel):
                state.trades.append({
                    "time": timestamp,
                    "type": "EXIT_TPS",
                    "price": state.trailingProfitStopLevel,
                    "size": abs(state.position_size),
                    "comment": f"Trailing Profit Stop Hit (Tier {state.trailingProfitStopTier})",
                })
                state.position_size = 0
                self._reset_position_state(state)
                return

        # --- RANGE TRAILING STOP ---
        # Activation
        if (
            self.config.ENABLE_RANGE_TRAILING_STOP
            and not state.trailingProfitStopActive
            and not state.rangeTrailingStopActive
            and (not self.config.ENABLE_ADVANCED_TP or not state.secondTPHit)
        ):
            if state.activationLevel is not None:
                if is_long and high >= state.activationLevel:
                    state.rangeTrailingStopActive = True
                    state.rangeTrailingStopLevel = self._get_range_based_stop_level(state, True)
                elif not is_long and low <= state.activationLevel:
                    state.rangeTrailingStopActive = True
                    state.rangeTrailingStopLevel = self._get_range_based_stop_level(state, False)
        
        # Update Level
        if self.config.ENABLE_RANGE_TRAILING_STOP and not state.trailingProfitStopActive and state.rangeTrailingStopActive:
            new_stop = self._get_range_based_stop_level(state, is_long)
            if new_stop is not None:
                if is_long:
                    if state.rangeTrailingStopLevel is None or new_stop > state.rangeTrailingStopLevel:
                        state.rangeTrailingStopLevel = new_stop
                else:
                    if state.rangeTrailingStopLevel is None or new_stop < state.rangeTrailingStopLevel:
                        state.rangeTrailingStopLevel = new_stop
            
            # Check Hit
            if state.rangeTrailingStopLevel is not None:
                stop_hit = False
                if is_long and low <= state.rangeTrailingStopLevel: stop_hit = True
                elif not is_long and high >= state.rangeTrailingStopLevel: stop_hit = True
                
                if stop_hit:
                    state.trades.append({
                        "time": timestamp,
                        "type": "EXIT_RTS",
                        "price": state.rangeTrailingStopLevel,
                        "size": abs(state.position_size),
                        "comment": "Range Trailing Stop Hit",
                    })
                    state.position_size = 0
                    self._reset_position_state(state)
                    return



    def _reset_position_state(self, state):
        state.entry_price = None
        state.firstTPLevel = None
        state.secondTPLevel = None
        state.firstTPHit = False
        state.secondTPHit = False
        state.breakevenActive = False
        state.breakevenLevel = None
        state.firstTPBar = None
        state.rangeTrailingStopActive = False
        state.rangeTrailingStopLevel = None
        state.activationLevel = None
        state.trailingProfitStopActive = False
        state.trailingProfitStopLevel = None
        state.trailingProfitSystemTriggered = False
        state.trailingProfitStopTier = 0
        state.highestPriceInPosition = None
        state.lowestPriceInPosition = None

    def _get_range_based_stop_level(self, state, is_long):
        # Pine: getRangeBasedStopLevel(isLong)
        # Long uses X-range-low, Short uses Y-range-high.
        if is_long:
            return state.x_range_low
        return state.y_range_high

    def _calculate_tp_levels(self, entry_price, is_long):
        # Simple percentage based TP for now, or match Pine logic if complex
        # Pine: calculateTPLevels
        tp1 = entry_price * (1 + self.config.FIRST_TP_PERCENT/100) if is_long else entry_price * (1 - self.config.FIRST_TP_PERCENT/100)
        tp2 = entry_price * (1 + self.config.SECOND_TP_PERCENT/100) if is_long else entry_price * (1 - self.config.SECOND_TP_PERCENT/100)
        return [tp1, tp2]

    def _calculate_activation_level(self, entry_price, is_long):
        # Pine: calculateRangeTrailingActivationLevel
        # Usually entry price + some offset or just entry price
        # Let's assume it activates after some profit
        if self.config.RANGE_TRAILING_ACTIVATION == 0:
            return entry_price
        
        offset = entry_price * (self.config.RANGE_TRAILING_ACTIVATION/100)
        return entry_price + offset if is_long else entry_price - offset

    def _generate_signal(self, state, index):
        signal = None
        
        # --- LONG ENTRY LOGIC ---
        # Pine: shouldOpenLong() => isDayAllowed() ... and isLongAllowedByMomentum and isNewBullishMomentumRange and condition_C
        
        # 1. Check Momentum Allowed
        # Pine: isLongAllowedByMomentum = momentumFavorsBullish or not enableMomentumFilter
        isLongAllowedByMomentum = state.momentumFavorsBullish or not self.config.ENABLE_MOMENTUM_FILTER
        
        # 2. Check New Momentum Range
        # Pine: isNewBullishMomentumRange = lastBullishMomentumBar != usedBullishMomentumBar
        isNewBullishMomentumRange = state.lastBullishMomentumBar != state.usedBullishMomentumBar
        
        if isLongAllowedByMomentum and isNewBullishMomentumRange and state.condition_C:
             # We have a signal!
             signal = "LONG"
             # Mark momentum as used
             state.usedBullishMomentumBar = state.lastBullishMomentumBar
             
             # Reset Condition C? Pine doesn't reset C immediately here, but C is stateful.
             # However, since we mark momentum as used, we won't enter again until new momentum.
             
        # --- SHORT ENTRY LOGIC ---
        # Pine: shouldOpenShort() => ... and isShortAllowedByMomentum and isNewBearishMomentumRange and condition_D
        
        # 1. Check Momentum Allowed
        isShortAllowedByMomentum = state.momentumFavorsBearish or not self.config.ENABLE_MOMENTUM_FILTER
        
        # 2. Check New Momentum Range
        isNewBearishMomentumRange = state.lastBearishMomentumBar != state.usedBearishMomentumBar
        
        if isShortAllowedByMomentum and isNewBearishMomentumRange and state.condition_D:
             signal = "SHORT"
             state.usedBearishMomentumBar = state.lastBearishMomentumBar
             
        return signal

    def _percent_diff(self, p1, p2):
        if p1 is None or p2 is None or p1 == 0: return 0.0
        return 100 * abs(p1 - p2) / p1
