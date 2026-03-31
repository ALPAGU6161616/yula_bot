import plotly.graph_objects as go
from plotly.subplots import make_subplots
import math
import pandas as pd

class Visualizer:
    def __init__(self):
        pass

    def plot_strategy(self, df, states, trades=None, config=None, max_display_candles=None):
        """
        Plots the candlestick chart with strategy overlays.
        :param df: DataFrame with 'timestamp', 'open', 'high', 'low', 'close'
        :param states: List of state dictionaries (or objects) corresponding to each candle
        :param trades: List of trade dictionaries (optional)
        :param config: Config-like object or dict (optional)
        :param max_display_candles: Downsample candles for faster rendering (optional)
        """
        fig = make_subplots(rows=1, cols=1, shared_xaxes=True, vertical_spacing=0.03)

        def get_val(obj, key):
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        def get_cfg(key: str, default):
            if config is None:
                return default
            if isinstance(config, dict):
                return config.get(key, default)
            return getattr(config, key, default)

        def normalize_number(value):
            if value is None:
                return None
            try:
                if pd.isna(value):
                    return None
            except Exception:
                pass
            try:
                return float(value)
            except Exception:
                return None

        def compress_steps(xs, ys):
            out_x = []
            out_y = []
            prev = object()
            for x, y in zip(xs, ys):
                y_norm = normalize_number(y)
                if y_norm != prev:
                    out_x.append(x)
                    out_y.append(y_norm)
                    prev = y_norm
            return out_x, out_y

        def add_step_line(name, xs, ys, color, width=1, dash=None):
            x2, y2 = compress_steps(xs, ys)
            if len(x2) < 2:
                return
            fig.add_trace(go.Scatter(
                x=x2,
                y=y2,
                mode="lines",
                name=name,
                line=dict(color=color, width=width, dash=dash, shape="hv"),
                connectgaps=False,
            ))

        def downsample_ohlc(input_df, input_states):
            if max_display_candles is None:
                return input_df, input_states
            try:
                max_points = int(max_display_candles)
            except Exception:
                return input_df, input_states
            if max_points <= 0 or len(input_df) <= max_points:
                return input_df, input_states

            # Prefer a faithful rolling window over aggregated candles (better for "live" updates).
            start = max(0, len(input_df) - max_points)
            df_ds = input_df.iloc[start:].reset_index(drop=True)
            states_ds = input_states[start:] if isinstance(input_states, list) else input_states
            return df_ds, states_ds

        def to_gmt3_datetime(value):
            if value is None:
                return None
            if isinstance(value, (int, float)):
                ts = pd.to_datetime(int(value), unit="ms")
            else:
                ts = pd.to_datetime(value)
            if isinstance(ts, pd.Timestamp) and ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            return ts + pd.Timedelta(hours=3)

        df, states = downsample_ohlc(df, states)

        plot_times = pd.to_datetime(df["timestamp"])
        if getattr(plot_times.dt, "tz", None) is not None:
            plot_times = plot_times.dt.tz_convert("UTC").dt.tz_localize(None)
        plot_times = plot_times + pd.Timedelta(hours=3)

        trades_filtered = None
        if trades:
            min_time = plot_times.min()
            max_time = plot_times.max()
            trades_filtered = []
            for t in trades:
                if not isinstance(t, dict):
                    continue
                t_ts = to_gmt3_datetime(t.get("time"))
                if t_ts is None:
                    continue
                if t_ts < min_time or t_ts > max_time:
                    continue
                t_copy = dict(t)
                t_copy["_time_gmt3"] = t_ts
                trades_filtered.append(t_copy)

        # 1. Candlestick Chart
        fig.add_trace(go.Candlestick(
            x=plot_times,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price',
            increasing_line_color='#089981', # TradingView Green
            decreasing_line_color='#F23645'  # TradingView Red
        ))

        show_xy_ranges = bool(get_cfg("SHOW_XY_RANGES", True))
        show_ls_ranges = bool(get_cfg("SHOW_LS_RANGES", True))
        show_mn_ranges = bool(get_cfg("SHOW_MN_RANGES", False))
        show_xy_fibs = bool(get_cfg("SHOW_XY_FIBS", False))
        show_ls_fibs = bool(get_cfg("SHOW_LS_FIBS", False))
        show_mn_fibs = bool(get_cfg("SHOW_MN_FIBS", False))

        def build_active_series(active_key, value_key):
            out = []
            for st in states:
                if not get_val(st, active_key):
                    out.append(None)
                else:
                    out.append(get_val(st, value_key))
            return out

        def build_series(value_key):
            out = []
            for st in states:
                out.append(get_val(st, value_key))
            return out

        def build_fib_series(active_key, fibs_key, level):
            out = []
            for st in states:
                if active_key and not get_val(st, active_key):
                    out.append(None)
                    continue
                fibs = get_val(st, fibs_key) or {}
                if not isinstance(fibs, dict):
                    out.append(None)
                    continue
                out.append(fibs.get(level))
            return out

        # 2. Ranges / Levels
        if show_xy_ranges:
            x_highs = build_active_series("x_range_active", "x_range_high")
            x_lows = build_active_series("x_range_active", "x_range_low")
            y_highs = build_active_series("y_range_active", "y_range_high")
            y_lows = build_active_series("y_range_active", "y_range_low")

            add_step_line("X High", plot_times, x_highs, color="#2962FF", width=1)
            add_step_line("X Low", plot_times, x_lows, color="#2962FF", width=1, dash="dash")
            add_step_line("Y High", plot_times, y_highs, color="#EF5350", width=1, dash="dash")
            add_step_line("Y Low", plot_times, y_lows, color="#EF5350", width=1)

        if show_ls_ranges:
            l_highs = build_series("l_range_high")
            l_lows = build_series("l_range_low")
            s_highs = build_series("s_range_high")
            s_lows = build_series("s_range_low")

            add_step_line("L High", plot_times, l_highs, color="#00C853", width=2)
            add_step_line("L Low", plot_times, l_lows, color="#00C853", width=2, dash="dot")
            add_step_line("S High", plot_times, s_highs, color="#FF9100", width=2, dash="dot")
            add_step_line("S Low", plot_times, s_lows, color="#FF9100", width=2)

        if show_mn_ranges:
            m_highs = build_active_series("m_range_active", "m_range_high")
            m_lows = build_active_series("m_range_active", "m_range_low")
            n_highs = build_active_series("n_range_active", "n_range_high")
            n_lows = build_active_series("n_range_active", "n_range_low")

            add_step_line("M High", plot_times, m_highs, color="#00E5FF", width=2)
            add_step_line("M Low", plot_times, m_lows, color="#00E5FF", width=2, dash="dot")
            add_step_line("N High", plot_times, n_highs, color="#EC407A", width=2, dash="dot")
            add_step_line("N Low", plot_times, n_lows, color="#EC407A", width=2)

        # 3. Fibonacci levels (optional)
        if show_xy_fibs:
            levels = [0.382, 0.5, 0.618, 0.705]
            for lvl in levels:
                add_step_line(f"X Fib {lvl}", plot_times, build_fib_series("x_range_active", "x_fibs", lvl), color="#42A5F5", width=1, dash="dot")
                add_step_line(f"Y Fib {lvl}", plot_times, build_fib_series("y_range_active", "y_fibs", lvl), color="#FF7043", width=1, dash="dot")

        if show_ls_fibs:
            levels = [0.382, 0.5, 0.618, 0.705]
            for lvl in levels:
                add_step_line(f"L Fib {lvl}", plot_times, build_fib_series(None, "l_fibs", lvl), color="#00E676", width=1, dash="dot")
                add_step_line(f"S Fib {lvl}", plot_times, build_fib_series(None, "s_fibs", lvl), color="#FFAB40", width=1, dash="dot")

        if show_mn_fibs:
            levels = [0.382, 0.5, 0.618, 0.705]
            for lvl in levels:
                add_step_line(f"M Fib {lvl}", plot_times, build_fib_series("m_range_active", "m_fibs", lvl), color="#18FFFF", width=1, dash="dot")
                add_step_line(f"N Fib {lvl}", plot_times, build_fib_series("n_range_active", "n_fibs", lvl), color="#FF4081", width=1, dash="dot")

        # 4. Signals (Markers) - TradingView Style with Dynamic Offset
        # Calculate dynamic offset based on visible price range
        price_min = df["low"].min()
        price_max = df["high"].max()
        price_range = price_max - price_min if price_max > price_min else price_max * 0.01
        # Use 3% of price range for marker offset (TradingView style)
        marker_offset = price_range * 0.03
        
        show_signal_markers = True
        if trades_filtered and any(t.get("type") in {"ENTRY_LONG", "ENTRY_SHORT"} for t in trades_filtered):
            show_signal_markers = False

        if show_signal_markers:
            long_signal_indices = []
            short_signal_indices = []

            for i in range(len(states)):
                state = states[i]
                sig = get_val(state, "signal")
                if sig == "LONG":
                    long_signal_indices.append(i)
                elif sig == "SHORT":
                    short_signal_indices.append(i)

            if long_signal_indices:
                # Use dynamic offset for LONG markers - position below candle low
                fig.add_trace(go.Scatter(
                    x=[plot_times.iloc[i] for i in long_signal_indices],
                    y=[df.iloc[i]["low"] - marker_offset for i in long_signal_indices],
                    mode="markers+text",
                    text=["LONG"] * len(long_signal_indices),
                    textposition="bottom center",
                    textfont=dict(color="#089981", size=11, family="Arial Black"),
                    marker=dict(
                        symbol="triangle-up",
                        size=20,
                        color="#089981",
                        line=dict(color="#FFFFFF", width=2),
                    ),
                    name="LONG",
                    hovertemplate="<b>LONG Entry</b><br>Time: %{x}<br>Price: %{y:.4f}<extra></extra>",
                ))

            if short_signal_indices:
                # Use dynamic offset for SHORT markers - position above candle high
                fig.add_trace(go.Scatter(
                    x=[plot_times.iloc[i] for i in short_signal_indices],
                    y=[df.iloc[i]["high"] + marker_offset for i in short_signal_indices],
                    mode="markers+text",
                    text=["SHORT"] * len(short_signal_indices),
                    textposition="top center",
                    textfont=dict(color="#F23645", size=11, family="Arial Black"),
                    marker=dict(
                        symbol="triangle-down",
                        size=20,
                        color="#F23645",
                        line=dict(color="#FFFFFF", width=2),
                    ),
                    name="SHORT",
                    hovertemplate="<b>SHORT Entry</b><br>Time: %{x}<br>Price: %{y:.4f}<extra></extra>",
                ))

        # 5. Trade Entries and Exits (Markers) - TradingView Style with Dynamic Offset
        if trades_filtered:
            # Define styles with offset direction: 'below' or 'above'
            trade_style = {
                "ENTRY_LONG": {"label": "LONG", "symbol": "triangle-up", "size": 22, "color": "#089981", "textpos": "bottom center", "offset_dir": "below"},
                "ENTRY_SHORT": {"label": "SHORT", "symbol": "triangle-down", "size": 22, "color": "#F23645", "textpos": "top center", "offset_dir": "above"},
                "EXIT_TP1": {"label": "TP1", "symbol": "circle", "size": 18, "color": "#9C27B0", "textpos": "top center", "offset_dir": "above"},
                "EXIT_TP2": {"label": "TP2", "symbol": "star", "size": 20, "color": "#FFD54F", "textpos": "top center", "offset_dir": "above"},
                "EXIT_BE": {"label": "BE", "symbol": "diamond", "size": 18, "color": "#B0BEC5", "textpos": "top center", "offset_dir": "above"},
                "EXIT_SL": {"label": "SL", "symbol": "x", "size": 20, "color": "#FF6D00", "textpos": "bottom center", "offset_dir": "below"},
                "EXIT_RTS": {"label": "RTS", "symbol": "x", "size": 20, "color": "#FF9100", "textpos": "top center", "offset_dir": "above"},
                "EXIT_TPS": {"label": "TPS", "symbol": "cross", "size": 20, "color": "#00E5FF", "textpos": "top center", "offset_dir": "above"},
                "EXIT_REV": {"label": "REV", "symbol": "square", "size": 18, "color": "#00B0FF", "textpos": "top center", "offset_dir": "above"},
            }

            grouped = {}
            for t in trades_filtered:
                t_type = t.get("type")
                if not t_type:
                    continue
                grouped.setdefault(t_type, []).append(t)

            for t_type, items in grouped.items():
                style = trade_style.get(t_type, None)
                if style is None:
                    continue

                xs = [t.get("_time_gmt3") or to_gmt3_datetime(t.get("time")) for t in items]
                # Apply dynamic offset based on direction
                offset_dir = style.get("offset_dir", "above")
                if offset_dir == "below":
                    ys = [(t.get("price") or 0) - marker_offset for t in items]
                else:
                    ys = [(t.get("price") or 0) + marker_offset for t in items]
                comments = [t.get("comment", "") for t in items]

                fig.add_trace(go.Scatter(
                    x=xs,
                    y=ys,
                    mode="markers+text",
                    text=[style["label"]] * len(items),
                    textposition=style["textpos"],
                    textfont=dict(color=style["color"], size=11, family="Arial Black"),
                    customdata=comments,
                    marker=dict(
                        symbol=style["symbol"],
                        size=style["size"],
                        color=style["color"],
                        line=dict(color="#FFFFFF", width=2),
                    ),
                    name=style["label"],
                    hovertemplate=f"<b>{style['label']}</b><br>Time: %{{x}}<br>Price: %{{y:.4f}}<br>%{{customdata}}<extra></extra>",
                ))

        # Layout Updates - TradingView Style
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#131722", # TV Dark Background
            plot_bgcolor="#131722",
            dragmode='pan', # Default to panning like TV
            hovermode='x unified', # Crosshair behavior
            xaxis_rangeslider_visible=False,
            height=800,
            xaxis=dict(
                showgrid=True, 
                gridcolor="#2A2E39",
                zeroline=False,
                showspikes=True, # Crosshair vertical line
                spikemode='across',
                spikesnap='cursor',
                showline=False,
                showticklabels=True,
                automargin=True,
                fixedrange=False, # Allow zooming/panning
                title_text="Time (UTC+3)",
            ),
            yaxis=dict(
                showgrid=True, 
                gridcolor="#2A2E39",
                zeroline=False,
                side="right", # Price on right like TV
                showspikes=True, # Crosshair horizontal line
                spikemode='across',
                spikesnap='cursor',
                showline=False,
                showticklabels=True,
                automargin=True,
                fixedrange=False # Allow zooming/panning by dragging axis
            ),
            margin=dict(l=10, r=95, t=30, b=55),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        # Enable scroll zoom
        fig.update_xaxes(constrain='domain')
        fig.update_yaxes(constrain='domain')
        
        return fig
