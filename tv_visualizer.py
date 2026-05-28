"""TradingView Lightweight Charts visualizer.

Replaces the Plotly-based `visualizer.py`. Produces a JSON payload that the
embedded JS template renders as a candlestick chart with strategy overlays
and trade markers.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tv_chart_template.html")
_LWC_JS_PATH = os.path.join(_ASSETS_DIR, "lightweight-charts.standalone.production.js")

# Display timezone offset (matches the GMT+3 shift used in visualizer.py).
# Lightweight Charts always renders timestamps as UTC, so we pre-shift the
# data so that UTC display lines up with the user's local market view.
_DISPLAY_TZ_OFFSET_HOURS = 3

_TEMPLATE_CACHE: Optional[str] = None
_LWC_JS_CACHE: Optional[str] = None


def _load_template() -> str:
    global _TEMPLATE_CACHE, _LWC_JS_CACHE
    if _TEMPLATE_CACHE is None:
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            _TEMPLATE_CACHE = f.read()
    if _LWC_JS_CACHE is None:
        with open(_LWC_JS_PATH, "r", encoding="utf-8") as f:
            _LWC_JS_CACHE = f.read()
    return _TEMPLATE_CACHE


def _get_val(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _get_cfg(config: Any, key: str, default: Any) -> Any:
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _to_unix_seconds(value: Any) -> Optional[int]:
    """Convert a timestamp-like value into UNIX seconds, shifted to display tz."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 1e12:  # already ms
            ts = pd.to_datetime(int(value), unit="ms", utc=True)
        else:
            ts = pd.to_datetime(int(value), unit="s", utc=True)
    else:
        ts = pd.to_datetime(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    shifted = ts + pd.Timedelta(hours=_DISPLAY_TZ_OFFSET_HOURS)
    return int(shifted.timestamp())


def _finite_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        f = float(value)
    except Exception:
        return None
    if not math.isfinite(f):
        return None
    return f


def _build_candles(df: pd.DataFrame) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    last_time: Optional[int] = None
    for _, row in df.iterrows():
        t = _to_unix_seconds(row["timestamp"])
        if t is None:
            continue
        # Lightweight Charts requires strictly increasing time, no duplicates.
        if last_time is not None and t <= last_time:
            continue
        out.append({
            "time": t,
            "open": _finite_or_none(row["open"]),
            "high": _finite_or_none(row["high"]),
            "low": _finite_or_none(row["low"]),
            "close": _finite_or_none(row["close"]),
        })
        last_time = t
    return out


def _compress_line(times: List[int], values: List[Optional[float]]) -> List[Dict[str, Any]]:
    """Drop runs of identical values; emit only state transitions.

    Mirrors visualizer.compress_steps — produces fewer points for step-line
    rendering. Gaps (None values) split the line into separate segments by
    introducing a whitespace point on each side.
    """
    out: List[Dict[str, Any]] = []
    prev = object()
    for t, v in zip(times, values):
        nv = _finite_or_none(v)
        if nv != prev:
            out.append({"time": t, "value": nv} if nv is not None else {"time": t})
            prev = nv
    return [p for p in out if "value" in p]


def _add_step_line(
    lines: List[Dict[str, Any]],
    line_id: str,
    times: List[int],
    values: List[Optional[float]],
    color: str,
    width: int = 1,
    style: str = "solid",
) -> None:
    data = _compress_line(times, values)
    if len(data) < 2:
        return
    lines.append({
        "id": line_id,
        "color": color,
        "width": width,
        "style": style,
        "step": True,
        "data": data,
    })


def _build_active_series(states: Iterable[Any], active_key: str, value_key: str) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for st in states:
        if not _get_val(st, active_key):
            out.append(None)
        else:
            out.append(_get_val(st, value_key))
    return out


def _build_plain_series(states: Iterable[Any], value_key: str) -> List[Optional[float]]:
    return [_get_val(st, value_key) for st in states]


def _build_range_boxes(
    states: List[Any],
    times: List[int],
    high_key: str,
    low_key: str,
    fill_color: str,
    border_color: str,
    active_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Detect contiguous range segments from state history and emit boxes.

    A new box is opened whenever (high, low) changes value while the range
    is active, mirroring Pine Script's behaviour where each level extension
    draws a new (overlapping) box. Adjacent boxes share an endpoint so the
    renderer can suppress the vertical seam between them and the chain reads
    as a single shape with horizontal step jogs.
    """
    boxes: List[Dict[str, Any]] = []
    cur_start: Optional[int] = None
    cur_high: Optional[float] = None
    cur_low: Optional[float] = None

    def close(end_time: int) -> None:
        if cur_start is None or cur_high is None or cur_low is None:
            return
        if end_time < cur_start:
            return
        boxes.append({
            "start": cur_start,
            "end": end_time,
            "high": cur_high,
            "low": cur_low,
            "fill": fill_color,
            "border": border_color,
            "border_left": True,
            "border_right": True,
        })

    for i, st in enumerate(states):
        h = _finite_or_none(_get_val(st, high_key))
        l = _finite_or_none(_get_val(st, low_key))
        is_active = h is not None and l is not None
        if active_key is not None:
            is_active = is_active and bool(_get_val(st, active_key))

        if not is_active:
            if cur_start is not None:
                # Real deactivation: close at previous bar (range no longer active).
                close(times[i - 1] if i > 0 else times[i])
                cur_start = None
                cur_high = None
                cur_low = None
            continue

        if cur_start is None:
            cur_start = times[i]
            cur_high = h
            cur_low = l
        elif h != cur_high or l != cur_low:
            # Step change inside an active chain: close at the transition bar
            # and reopen at the same time so the boxes share an endpoint.
            close(times[i])
            cur_start = times[i]
            cur_high = h
            cur_low = l

    if cur_start is not None and times:
        close(times[-1])

    # Decide how each adjacent pair connects. Two boxes that share an endpoint
    # belong to the same visual chain ONLY when their price ranges overlap — a
    # genuine extension where the level steps up/down a bit. When the ranges are
    # disjoint (a brand-new range replaced the old one at a different level) the
    # boxes stay separate so a full outer border divides them.
    for i in range(len(boxes) - 1):
        cur = boxes[i]
        nxt = boxes[i + 1]
        if cur["end"] != nxt["start"]:
            continue
        overlap = max(cur["low"], nxt["low"]) <= min(cur["high"], nxt["high"])
        if not overlap:
            # Disjoint ranges: keep both vertical borders (they coincide into a
            # single clean separator at the shared X).
            continue
        cur["border_right"] = False
        nxt["border_left"] = False
        # Step jog at the shared X coordinate, drawn on cur's right edge, to
        # close the chain outline where one side extends past the other.
        if cur["high"] != nxt["high"]:
            cur["jog_right_top"] = nxt["high"]
        if cur["low"] != nxt["low"]:
            cur["jog_right_bottom"] = nxt["low"]

    return boxes


def _build_fib_series(
    states: Iterable[Any],
    active_key: Optional[str],
    fibs_key: str,
    level: float,
) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for st in states:
        if active_key and not _get_val(st, active_key):
            out.append(None)
            continue
        fibs = _get_val(st, fibs_key) or {}
        if not isinstance(fibs, dict):
            out.append(None)
            continue
        out.append(fibs.get(level))
    return out


# Lightweight Charts v5 supports shapes: arrowUp | arrowDown | circle | square.
# Plotly's diamond/star/x/cross don't exist — we substitute and rely on text+color
# to disambiguate. Color palette matches the existing visualizer.
_TRADE_STYLE: Dict[str, Dict[str, str]] = {
    "ENTRY_LONG":  {"shape": "arrowUp",   "color": "#089981", "position": "belowBar", "text": "LONG"},
    "ENTRY_SHORT": {"shape": "arrowDown", "color": "#F23645", "position": "aboveBar", "text": "SHORT"},
    "EXIT_TP1":    {"shape": "circle",    "color": "#9C27B0", "position": "aboveBar", "text": "TP1"},
    "EXIT_TP2":    {"shape": "square",    "color": "#FFD54F", "position": "aboveBar", "text": "TP2"},
    "EXIT_BE":     {"shape": "square",    "color": "#B0BEC5", "position": "aboveBar", "text": "BE"},
    "EXIT_SL":     {"shape": "circle",    "color": "#FF6D00", "position": "belowBar", "text": "SL"},
    "EXIT_RTS":    {"shape": "circle",    "color": "#FF9100", "position": "aboveBar", "text": "RTS"},
    "EXIT_TPS":    {"shape": "circle",    "color": "#00E5FF", "position": "aboveBar", "text": "TPS"},
    "EXIT_REV":    {"shape": "square",    "color": "#00B0FF", "position": "aboveBar", "text": "REV"},
    "EXIT_STRUCT": {"shape": "square",    "color": "#D32F2F", "position": "belowBar", "text": "STOP"},
}


def build_chart_payload(
    df: pd.DataFrame,
    states: List[Any],
    trades: Optional[List[Dict[str, Any]]] = None,
    config: Any = None,
    *,
    symbol: str = "",
    timeframe: str = "",
    live_stream_url: Optional[str] = None,
    max_display_candles: Optional[int] = None,
    view_from: Any = None,
    view_to: Any = None,
) -> Dict[str, Any]:
    """Build the JSON payload consumed by the TV chart template."""

    if max_display_candles and len(df) > max_display_candles:
        start = max(0, len(df) - int(max_display_candles))
        df = df.iloc[start:].reset_index(drop=True)
        states = states[start:] if isinstance(states, list) else states

    candles = _build_candles(df)
    times = [c["time"] for c in candles]

    # States and candles can drift in length; truncate states to match the
    # candle stream we actually emit (after dedup).
    states_aligned = list(states)[: len(times)] if states else []

    lines: List[Dict[str, Any]] = []
    boxes: List[Dict[str, Any]] = []

    show_xy_ranges = bool(_get_cfg(config, "SHOW_XY_RANGES", True))
    show_ls_ranges = bool(_get_cfg(config, "SHOW_LS_RANGES", True))
    show_mn_ranges = bool(_get_cfg(config, "SHOW_MN_RANGES", False))
    show_xy_fibs   = bool(_get_cfg(config, "SHOW_XY_FIBS", False))
    show_ls_fibs   = bool(_get_cfg(config, "SHOW_LS_FIBS", False))
    show_mn_fibs   = bool(_get_cfg(config, "SHOW_MN_FIBS", False))

    # Palette matched to the Pine Script reference: X=green (long trigger),
    # Y=red (short trigger), L=blue (long momentum), S=purple (short momentum).
    # Fills are semi-transparent so overlapping ranges remain readable; borders
    # are nearly opaque to keep edges sharp on a dark background.
    PAL = {
        "x": ("rgba( 76, 175,  80, 0.14)", "rgba( 76, 175,  80, 0.90)"),
        "y": ("rgba(239,  83,  80, 0.14)", "rgba(239,  83,  80, 0.90)"),
        "l": ("rgba( 41,  98, 255, 0.14)", "rgba( 41,  98, 255, 0.90)"),
        "s": ("rgba(171,  71, 188, 0.14)", "rgba(171,  71, 188, 0.90)"),
        "m": ("rgba( 38, 198, 218, 0.14)", "rgba( 38, 198, 218, 0.90)"),
        "n": ("rgba(236,  64, 122, 0.14)", "rgba(236,  64, 122, 0.90)"),
    }

    if show_xy_ranges and states_aligned:
        boxes.extend(_build_range_boxes(states_aligned, times, "x_range_high", "x_range_low",
                                         PAL["x"][0], PAL["x"][1], active_key="x_range_active"))
        boxes.extend(_build_range_boxes(states_aligned, times, "y_range_high", "y_range_low",
                                         PAL["y"][0], PAL["y"][1], active_key="y_range_active"))

    if show_ls_ranges and states_aligned:
        # L and S ranges don't carry an explicit active flag — their values
        # themselves act as the activity signal.
        boxes.extend(_build_range_boxes(states_aligned, times, "l_range_high", "l_range_low",
                                         PAL["l"][0], PAL["l"][1]))
        boxes.extend(_build_range_boxes(states_aligned, times, "s_range_high", "s_range_low",
                                         PAL["s"][0], PAL["s"][1]))

    if show_mn_ranges and states_aligned:
        boxes.extend(_build_range_boxes(states_aligned, times, "m_range_high", "m_range_low",
                                         PAL["m"][0], PAL["m"][1], active_key="m_range_active"))
        boxes.extend(_build_range_boxes(states_aligned, times, "n_range_high", "n_range_low",
                                         PAL["n"][0], PAL["n"][1], active_key="n_range_active"))

    fib_levels = [0.382, 0.5, 0.618, 0.705]
    # Fib lines share the range hue so overlays read as a single unit.
    fib_xy_x = "rgba( 76, 175,  80, 0.65)"
    fib_xy_y = "rgba(239,  83,  80, 0.65)"
    fib_ls_l = "rgba( 41,  98, 255, 0.65)"
    fib_ls_s = "rgba(171,  71, 188, 0.65)"
    fib_mn_m = "rgba( 38, 198, 218, 0.65)"
    fib_mn_n = "rgba(236,  64, 122, 0.65)"
    if show_xy_fibs and states_aligned:
        for lvl in fib_levels:
            _add_step_line(lines, f"x_fib_{lvl}", times, _build_fib_series(states_aligned, "x_range_active", "x_fibs", lvl), fib_xy_x, 1, "dotted")
            _add_step_line(lines, f"y_fib_{lvl}", times, _build_fib_series(states_aligned, "y_range_active", "y_fibs", lvl), fib_xy_y, 1, "dotted")
    if show_ls_fibs and states_aligned:
        for lvl in fib_levels:
            _add_step_line(lines, f"l_fib_{lvl}", times, _build_fib_series(states_aligned, None, "l_fibs", lvl), fib_ls_l, 1, "dotted")
            _add_step_line(lines, f"s_fib_{lvl}", times, _build_fib_series(states_aligned, None, "s_fibs", lvl), fib_ls_s, 1, "dotted")
    if show_mn_fibs and states_aligned:
        for lvl in fib_levels:
            _add_step_line(lines, f"m_fib_{lvl}", times, _build_fib_series(states_aligned, "m_range_active", "m_fibs", lvl), fib_mn_m, 1, "dotted")
            _add_step_line(lines, f"n_fib_{lvl}", times, _build_fib_series(states_aligned, "n_range_active", "n_fibs", lvl), fib_mn_n, 1, "dotted")

    markers: List[Dict[str, Any]] = []

    trade_types_present = {t.get("type") for t in (trades or []) if isinstance(t, dict)}
    signal_overrides_present = bool(trade_types_present & {"ENTRY_LONG", "ENTRY_SHORT"})

    if not signal_overrides_present and states_aligned:
        for i, st in enumerate(states_aligned):
            sig = _get_val(st, "signal")
            if sig == "LONG":
                markers.append({
                    "time": times[i], "position": "belowBar",
                    "color": "#089981", "shape": "arrowUp", "text": "LONG",
                })
            elif sig == "SHORT":
                markers.append({
                    "time": times[i], "position": "aboveBar",
                    "color": "#F23645", "shape": "arrowDown", "text": "SHORT",
                })

    if trades:
        min_t = times[0] if times else None
        max_t = times[-1] if times else None
        for t in trades:
            if not isinstance(t, dict):
                continue
            ttype = t.get("type")
            style = _TRADE_STYLE.get(ttype)
            if not style:
                continue
            ts = _to_unix_seconds(t.get("time"))
            if ts is None:
                continue
            if min_t is not None and (ts < min_t or ts > max_t):
                continue
            comment = t.get("comment") or ""
            text = style["text"]
            if comment:
                text = f"{text} ({comment})"
            markers.append({
                "time": ts,
                "position": style["position"],
                "color": style["color"],
                "shape": style["shape"],
                "text": text,
                "size": 2,
            })

    # Markers must be sorted by time for LWC.
    markers.sort(key=lambda m: m["time"])

    payload: Dict[str, Any] = {
        "candles": candles,
        "lines": lines,
        "boxes": boxes,
        "markers": markers,
        "config": {"symbol": symbol, "timeframe": timeframe, "theme": "dark"},
    }
    if live_stream_url:
        payload["live"] = {"stream_url": live_stream_url}

    if view_from is not None and view_to is not None:
        vf = _to_unix_seconds(view_from)
        vt = _to_unix_seconds(view_to)
        if vf is not None and vt is not None:
            if vf > vt:
                vf, vt = vt, vf
            payload["view"] = {"from": vf, "to": vt}

    return payload


def render_tv_chart(payload: Dict[str, Any], height: int = 720) -> None:
    """Render the TV chart inside a Streamlit page via an inlined iframe."""
    from streamlit.components.v1 import html as st_html

    template = _load_template()
    js = _LWC_JS_CACHE or ""
    payload_json = json.dumps(payload, default=str, allow_nan=False)

    # Two-step substitution: JS bundle first (large), then payload.
    html_str = template.replace("__LIGHTWEIGHT_CHARTS_JS__", js)
    html_str = html_str.replace("__PAYLOAD__", payload_json)
    st_html(html_str, height=height, scrolling=False)


__all__ = ["build_chart_payload", "render_tv_chart"]
