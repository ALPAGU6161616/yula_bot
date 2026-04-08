import os
from dotenv import load_dotenv

load_dotenv()

def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

class Config:
    # API Credentials
    API_KEY = os.getenv("BINANCE_API_KEY", "YOUR_API_KEY")
    API_SECRET = os.getenv("BINANCE_API_SECRET", "YOUR_API_SECRET")
    
    # Trading Settings
    SYMBOL = "BTC/USDT"
    TIMEFRAME = "15m"  # Default timeframe
    HISTORICAL_CANDLE_LIMIT = 10000
    PAIR_HISTORY_LIMITS = os.getenv("PAIR_HISTORY_LIMITS", "")

    # Execution Settings
    # Use DRY-RUN by default to prevent accidental live orders.
    LIVE_TRADING = _env_bool("LIVE_TRADING", False)
    USE_TESTNET = _env_bool("USE_TESTNET", False)
    LEVERAGE = _env_int("LEVERAGE", 1)
    ORDER_NOTIONAL_USDT = _env_float("ORDER_NOTIONAL_USDT", 50.0)
    
    # General Settings
    # NOTE: In the PineScript this corresponds to "Maximum Line Length" and is used for
    # expiring touch/range tracking; it should NOT be used as an exchange fetch limit.
    MAX_LINE_LENGTH = 9999999
    # Backward-compatible name used by parts of the Python port.
    MAX_LOOKBACK = MAX_LINE_LENGTH
    MIN_BARS = 1
    
    # Fibonacci Constants
    FIB_382 = 0.382
    FIB_500 = 0.500
    FIB_618 = 0.618
    FIB_705 = 0.705
    
    # Strategy Inputs
    X_FIB_LEVEL_CHOICE = FIB_618  # Default from Pine
    Y_FIB_LEVEL_CHOICE = FIB_618  # Default from Pine
    
    # Momentum Filter Settings
    ENABLE_MOMENTUM_FILTER = True
    MOMENTUM_MULTIPLIER = 1.0
    SHOW_MOMENTUM_INFO = False
    ENABLE_MOMENTUM_RANGE_BREAK_FILTER = False
    
    # Momentum Tolerance
    MOMENTUM_TOLERANCE_PERCENT = 15.0
    ENABLE_MOMENTUM_TOLERANCE = True
    
    # Forbidden Hours (GMT+3)
    ENABLE_FORBIDDEN_HOURS = False
    FORBIDDEN_START_HOUR = 0
    FORBIDDEN_START_MINUTE = 0
    FORBIDDEN_END_HOUR = 5
    FORBIDDEN_END_MINUTE = 0
    
    # Advanced TP System
    ENABLE_ADVANCED_TP = _env_bool("ENABLE_ADVANCED_TP", True)
    FIRST_TP_PERCENT = _env_float("FIRST_TP_PERCENT", 5.0)
    FIRST_TP_QUANTITY = _env_float("FIRST_TP_QUANTITY", 20.0)
    SECOND_TP_PERCENT = _env_float("SECOND_TP_PERCENT", 99.0)
    ENABLE_BREAKEVEN_AFTER_FIRST_TP = _env_bool("ENABLE_BREAKEVEN_AFTER_FIRST_TP", True)
    
    # Range Trailing Stop
    ENABLE_RANGE_TRAILING_STOP = True
    RANGE_TRAILING_ACTIVATION = 10.0
    
    # Trailing Profit Stop
    ENABLE_TRAILING_PROFIT_STOP = True
    TRAILING_PROFIT_LOSS_THRESHOLD_1 = 10.0
    TRAILING_PROFIT_TAKE_LEVEL_1 = 0.1
    TRAILING_PROFIT_LOSS_THRESHOLD_2 = 99.0
    TRAILING_PROFIT_TAKE_LEVEL_2 = 1.0
    TRAILING_PROFIT_LOSS_THRESHOLD_3 = 99.0
    TRAILING_PROFIT_TAKE_LEVEL_3 = 3.0
    
    # Risk Management
    MAX_LOSS_PERCENTAGE = 99.0
    ENABLE_MAX_LOSS_PROTECTION = False

    # Minimum bar conditions (Pine: Min Bars Between Touch 2 and 3 ...)
    MIN_BARS_BETWEEN_TOUCH_2_3_XY = 1
    MIN_BARS_BETWEEN_TOUCH_2_3_LS = 1
    MIN_BARS_BETWEEN_TOUCH_2_3_MN = 1
    
    # C/D Condition Threshold Settings
    ENABLE_CD_THRESHOLD = False
    CD_THRESHOLD_PERCENT = 1.0

    # Day Filter Settings
    ENABLE_DAY_FILTER = False
    TRADE_ON_MONDAY = False
    TRADE_ON_TUESDAY = False
    TRADE_ON_WEDNESDAY = False
    TRADE_ON_THURSDAY = False
    TRADE_ON_FRIDAY = False
    TRADE_ON_SATURDAY = False
    TRADE_ON_SUNDAY = False
    
    # Month Filter Settings
    ENABLE_MONTH_FILTER = False
    TRADE_IN_JANUARY = True
    TRADE_IN_FEBRUARY = True
    TRADE_IN_MARCH = True
    TRADE_IN_APRIL = True
    TRADE_IN_MAY = True
    TRADE_IN_JUNE = True
    TRADE_IN_JULY = True
    TRADE_IN_AUGUST = True
    TRADE_IN_SEPTEMBER = True
    TRADE_IN_OCTOBER = True
    TRADE_IN_NOVEMBER = True
    TRADE_IN_DECEMBER = True

    # Pending Entry
    ENABLE_PENDING_ENTRY = True

    # Visualization Settings
    SHOW_XY_RANGES = False
    SHOW_XY_FIBS = False
    SHOW_LS_RANGES = True
    SHOW_LS_FIBS = False
    SHOW_MN_RANGES = False
    SHOW_MN_FIBS = False
    SHOW_STATUS_PANEL = False
    USE_OLD_CONDITION_LABELS = False

    # Label Settings
    SHOW_X_LABELS = True
    SHOW_Y_LABELS = True
    SHOW_L_LABELS = True
    SHOW_S_LABELS = True
    SHOW_M_LABELS = True
    SHOW_N_LABELS = True
    SHOW_CONDITION_LABELS = False

    # --- Detailed Touch Settings ---
    
    # X Range (Long)
    X1_BAND = "lower"
    X2_BAND = "upper"
    X2_COMPARE_WITH = "touch1"
    X2_SHOULD_BE = "above"
    X2_MIN_DIST_PCT = 5.0
    X3_MIN_DIST_BELOW_X2_PCT = 1.0

    # Y Range (Short)
    Y1_BAND = "upper"
    Y2_BAND = "lower"
    Y2_COMPARE_WITH = "touch1"
    Y2_SHOULD_BE = "below"
    Y2_MIN_DIST_PCT = 5.0
    Y3_MIN_DIST_ABOVE_Y2_PCT = 1.0 # Note: Image says "Above Y2" for Short Touch 3

    # L Range (Long Momentum)
    L1_BAND = "lower"
    L2_BAND = "upper"
    L2_COMPARE_WITH = "touch1"
    L2_SHOULD_BE = "above"
    L2_MIN_DIST_PCT = 10.0
    L3_MIN_DIST_BELOW_L2_PCT = 5.0

    # S Range (Short Momentum)
    S1_BAND = "upper"
    S2_BAND = "lower"
    S2_COMPARE_WITH = "touch1"
    S2_SHOULD_BE = "below"
    S2_MIN_DIST_PCT = 10.0
    S3_MIN_DIST_ABOVE_S2_PCT = 5.0

    # M Range (Long)
    M1_BAND = "lower"
    M2_BAND = "upper"
    M2_COMPARE_WITH = "touch1"
    M2_SHOULD_BE = "above"
    M2_MIN_DIST_PCT = 0.1
    M3_MIN_DIST_BELOW_M2_PCT = 0.1

    # N Range (Short)
    N1_BAND = "upper"
    N2_BAND = "lower"
    N2_COMPARE_WITH = "touch1"
    N2_SHOULD_BE = "below"
    N2_MIN_DIST_PCT = 0.1
    N3_MIN_DIST_ABOVE_N2_PCT = 0.1
