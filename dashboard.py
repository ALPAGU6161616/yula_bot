import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import ccxt
import plotly.io as pio
import plotly.graph_objects as go
import json
import hashlib
import queue
from io import BytesIO
from config import Config
from data_manager import DataManager
from yula_strategy import YulaStrategy, YulaState
from trader import Trader
from visualizer import Visualizer
from binance_ws import BinanceFuturesKlineStream, ccxt_symbol_to_binance_symbol
import time
import datetime as dt
import math

TRADE_PAIRS_TV = [
    "YGGUSDT.P",
    "TAOUSDT.P",
    "MAVUSDT.P",
    "MANTAUSDT.P",
    "LINKUSDT.P",
    "ATAUSDT.P",
    "ARUSDT.P",
    "ARBUSDT.P",
    "AAVEUSDT.P",
]

DEFAULT_TRADE_PAIRS_TV = [
    "TAOUSDT.P",
    "MAVUSDT.P",
    "MANTAUSDT.P",
    "ARBUSDT.P",
]

DATA_CACHE_VERSION = 2
REPLAY_STEP = 1
REPLAY_SPEED = 5.0

TV_AXIS_SCALE_POST_SCRIPT = r"""
(function(){
  const gd = document.getElementById('{plot_id}');
  if(!gd || !window.Plotly){ return; }

  let dragging = false;
  let axis = null; // 'x' or 'y'
  let startClientX = 0;
  let startClientY = 0;
  let startXRange = null;
  let startYRange = null;
  let anchorX = null;
  let anchorY = null;

  let rafId = null;
  let pendingUpdate = null;

  function toMs(v){
    if(v === null || v === undefined) return null;
    if(typeof v === 'number') return v;
    const d = new Date(v);
    const t = d.getTime();
    return Number.isFinite(t) ? t : null;
  }

  function getSize(){
    return gd._fullLayout && gd._fullLayout._size ? gd._fullLayout._size : null;
  }

  function scheduleRelayout(update){
    pendingUpdate = Object.assign(pendingUpdate || {}, update);
    if(rafId) return;
    rafId = requestAnimationFrame(function(){
      const u = pendingUpdate;
      pendingUpdate = null;
      rafId = null;
      try { Plotly.relayout(gd, u); } catch(e) {}
    });
  }

  function getAxes(){
    const fl = gd._fullLayout || {};
    const xaxis = fl.xaxis;
    const yaxis = fl.yaxis;
    const xr = xaxis && xaxis.range ? xaxis.range.slice() : null;
    const yr = yaxis && yaxis.range ? yaxis.range.slice() : null;
    return {xaxis, yaxis, xr, yr};
  }

  function onMouseDown(e){
    // Ignore right/middle click
    if(e.button !== 0) return;
    const size = getSize();
    if(!size) return;

    const rect = gd.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const left = size.l;
    const right = size.l + size.w;
    const top = size.t;
    const bottom = size.t + size.h;

    const inYScale = (x >= right && x <= right + size.r && y >= top && y <= bottom);
    const inXScale = (y >= bottom && y <= bottom + size.b && x >= left && x <= right);

    if(!(inYScale || inXScale)) return;

    // Prevent Plotly default axis drag (pan)
    e.preventDefault();
    e.stopPropagation();

    const {xaxis, yaxis, xr, yr} = getAxes();

    dragging = true;
    startClientX = e.clientX;
    startClientY = e.clientY;

    if(inYScale && yr){
      axis = 'y';
      startYRange = yr.slice();

      let a = null;
      if(yaxis && typeof yaxis.p2c === 'function'){
        const py = y - top;
        const v = yaxis.p2c(py);
        if(typeof v === 'number' && Number.isFinite(v)) a = v;
      }
      if(a === null){
        a = (startYRange[0] + startYRange[1]) / 2;
      }
      anchorY = a;
      document.body.style.cursor = 'ns-resize';
    } else if(inXScale && xr){
      axis = 'x';
      startXRange = xr.slice();

      const x0 = toMs(startXRange[0]);
      const x1 = toMs(startXRange[1]);
      if(x0 !== null && x1 !== null){
        let a = null;
        if(xaxis && typeof xaxis.p2c === 'function'){
          const px = x - left;
          const v = xaxis.p2c(px);
          const t = toMs(v);
          if(t !== null) a = t;
        }
        if(a === null){
          a = (x0 + x1) / 2;
        }
        anchorX = a;
      } else {
        anchorX = null;
      }
      document.body.style.cursor = 'ew-resize';
    } else {
      dragging = false;
      axis = null;
      return;
    }

    window.addEventListener('mousemove', onMouseMove, true);
    window.addEventListener('mouseup', onMouseUp, true);
  }

  function onMouseMove(e){
    if(!dragging || !axis) return;
    e.preventDefault();
    e.stopPropagation();

    if(axis === 'y'){
      if(!startYRange) return;
      const dy = e.clientY - startClientY;
      const scale = Math.exp(dy * 0.003);
      const y0 = startYRange[0];
      const y1 = startYRange[1];
      const a = anchorY;
      let ny0 = a + (y0 - a) * scale;
      let ny1 = a + (y1 - a) * scale;
      if(!Number.isFinite(ny0) || !Number.isFinite(ny1) || ny0 === ny1) return;
      if(ny0 > ny1){ const t = ny0; ny0 = ny1; ny1 = t; }
      const minRange = 1e-12;
      if(Math.abs(ny1 - ny0) < minRange) return;
      scheduleRelayout({'yaxis.autorange': false, 'yaxis.range': [ny0, ny1]});
    } else if(axis === 'x'){
      if(!startXRange || anchorX === null) return;
      const dx = e.clientX - startClientX;
      const scale = Math.exp(-dx * 0.003);
      const x0 = toMs(startXRange[0]);
      const x1 = toMs(startXRange[1]);
      if(x0 === null || x1 === null) return;
      const a = anchorX;
      let nx0 = a + (x0 - a) * scale;
      let nx1 = a + (x1 - a) * scale;
      if(!Number.isFinite(nx0) || !Number.isFinite(nx1) || nx0 === nx1) return;
      if(nx0 > nx1){ const t = nx0; nx0 = nx1; nx1 = t; }
      const minRangeMs = 60 * 1000; // 1 minute
      if((nx1 - nx0) < minRangeMs) return;
      scheduleRelayout({'xaxis.autorange': false, 'xaxis.range': [new Date(nx0), new Date(nx1)]});
    }
  }

  function onMouseUp(e){
    if(!dragging) return;
    dragging = false;
    axis = null;
    startXRange = null;
    startYRange = null;
    anchorX = null;
    anchorY = null;
    document.body.style.cursor = '';
    window.removeEventListener('mousemove', onMouseMove, true);
    window.removeEventListener('mouseup', onMouseUp, true);
  }

  gd.addEventListener('mousedown', onMouseDown, true);
})();
"""

TV_REALTIME_CANDLE_POST_SCRIPT = r"""
(function(){
  const gd = document.getElementById('{plot_id}');
  if(!gd || !window.Plotly || !window.WebSocket){ return; }

  const STREAM = "__STREAM__";
  const WS_URL = "wss://fstream.binance.com/ws/" + STREAM;
  const MAX_POINTS = __MAX_POINTS__;
  const TZ_SHIFT_MS = __TZ_SHIFT_MS__;
  const AUTO_SCROLL = __AUTO_SCROLL__;

  let ws = null;
  let reconnectTimer = null;

  let liveTraceIdx = null;
  let priceTraceIdx = null;
  let lastAppendedShiftedOpenMs = null;

  let lastPrice = null;
  let lastPriceStr = null;
  let lastCloseTimeMs = null;
  let lastOpenTimeMs = null;
  let lastOpen = null;
  let lastHigh = null;
  let lastLow = null;

  let overlayReady = false;
  let shapeIndex = null;
  let annoIndex = null;

  let rafId = null;
  let pendingUpdate = null;

  function scheduleRelayout(update){
    pendingUpdate = Object.assign(pendingUpdate || {}, update);
    if(rafId) return;
    rafId = requestAnimationFrame(function(){
      const u = pendingUpdate;
      pendingUpdate = null;
      rafId = null;
      try { Plotly.relayout(gd, u); } catch(e) {}
    });
  }

  function findLiveTraceIndex(){
    for(let i=0;i<gd.data.length;i++){
      const t = gd.data[i];
      if(t && t.type === 'candlestick' && t.name === 'LIVE'){
        return i;
      }
    }
    return null;
  }

  function findPriceTraceIndex(){
    for(let i=0;i<gd.data.length;i++){
      const t = gd.data[i];
      if(t && t.type === 'candlestick' && t.name === 'Price'){
        return i;
      }
    }
    for(let i=0;i<gd.data.length;i++){
      const t = gd.data[i];
      if(t && t.type === 'candlestick' && t.name !== 'LIVE'){
        return i;
      }
    }
    return null;
  }

  function initLastAppended(){
    if(priceTraceIdx === null){
      priceTraceIdx = findPriceTraceIndex();
    }
    if(priceTraceIdx === null) return;
    const xArr = gd.data[priceTraceIdx] && gd.data[priceTraceIdx].x ? gd.data[priceTraceIdx].x : null;
    if(!xArr || !xArr.length) return;
    const t = new Date(xArr[xArr.length - 1]).getTime();
    if(Number.isFinite(t)) lastAppendedShiftedOpenMs = t;
  }

  function tryAutoScroll(lastBarShiftedOpenMs, barMs){
    if(!AUTO_SCROLL) return;
    const xaxis = gd._fullLayout && gd._fullLayout.xaxis ? gd._fullLayout.xaxis : null;
    if(!xaxis || !xaxis.range || xaxis.range.length < 2) return;

    const x0 = new Date(xaxis.range[0]).getTime();
    const x1 = new Date(xaxis.range[1]).getTime();
    if(!Number.isFinite(x0) || !Number.isFinite(x1)) return;

    const pad = Math.max(barMs, 60 * 1000);
    const eps = pad * 2;
    if(Math.abs(x1 - (lastBarShiftedOpenMs + pad)) > eps && Math.abs(x1 - lastBarShiftedOpenMs) > eps) return;

    const width = x1 - x0;
    if(!(width > 0)) return;
    const newX1 = lastBarShiftedOpenMs + pad;
    const newX0 = newX1 - width;
    scheduleRelayout({'xaxis.autorange': false, 'xaxis.range': [new Date(newX0), new Date(newX1)]});
  }

  function ensureOverlay(){
    if(overlayReady) return;
    liveTraceIdx = findLiveTraceIndex();
    priceTraceIdx = findPriceTraceIndex();
    initLastAppended();

    const shapes = (gd.layout.shapes || []).slice();
    const annotations = (gd.layout.annotations || []).slice();

    shapeIndex = shapes.length;
    annoIndex = annotations.length;

    shapes.push({
      type: 'line',
      xref: 'paper',
      x0: 0,
      x1: 1,
      yref: 'y',
      y0: 0,
      y1: 0,
      line: {color: '#A0A0A0', width: 1, dash: 'dot'}
    });

    annotations.push({
      xref: 'paper',
      x: 1,
      xanchor: 'left',
      xshift: 6,
      yref: 'y',
      y: 0,
      text: '',
      showarrow: false,
      bgcolor: '#FFFFFF',
      bordercolor: '#FFFFFF',
      borderwidth: 1,
      font: {color: '#000000', size: 12},
      align: 'left'
    });

    scheduleRelayout({shapes: shapes, annotations: annotations});
    overlayReady = true;
  }

  function pad2(n){ return String(n).padStart(2,'0'); }

  function formatRemaining(ms){
    if(ms < 0) ms = 0;
    const total = Math.floor(ms / 1000);
    const m = Math.floor(total / 60);
    const s = total % 60;
    if(m >= 60){
      const h = Math.floor(m / 60);
      const mm = m % 60;
      return pad2(h) + ':' + pad2(mm) + ':' + pad2(s);
    }
    return pad2(m) + ':' + pad2(s);
  }

  function updateOverlay(){
    if(lastPrice === null || lastCloseTimeMs === null) return;
    ensureOverlay();
    const remaining = lastCloseTimeMs - Date.now();
    const t = formatRemaining(remaining);
    const priceText = lastPriceStr !== null ? lastPriceStr : String(lastPrice);
    const text = priceText + '<br>' + t;

    const u = {};
    u[`shapes[${shapeIndex}].y0`] = lastPrice;
    u[`shapes[${shapeIndex}].y1`] = lastPrice;
    u[`annotations[${annoIndex}].y`] = lastPrice;
    u[`annotations[${annoIndex}].text`] = text;
    scheduleRelayout(u);
  }

  function updateLiveCandle(){
    if(liveTraceIdx === null){
      liveTraceIdx = findLiveTraceIndex();
      if(liveTraceIdx === null) return;
    }
    if(lastOpenTimeMs === null || lastOpen === null || lastHigh === null || lastLow === null || lastPrice === null) return;
    try{
      Plotly.restyle(gd, {
        x: [[new Date(lastOpenTimeMs + TZ_SHIFT_MS)]],
        open: [[lastOpen]],
        high: [[lastHigh]],
        low: [[lastLow]],
        close: [[lastPrice]]
      }, [liveTraceIdx]);
    } catch(e) {}
  }

  function appendClosedToHistory(openTime, open, high, low, close, barMs){
    if(priceTraceIdx === null){
      priceTraceIdx = findPriceTraceIndex();
      initLastAppended();
    }
    if(priceTraceIdx === null) return;

    const shiftedOpenMs = openTime + TZ_SHIFT_MS;
    if(lastAppendedShiftedOpenMs !== null && shiftedOpenMs <= lastAppendedShiftedOpenMs) return;
    lastAppendedShiftedOpenMs = shiftedOpenMs;

    try{
      Plotly.extendTraces(gd, {
        x: [[new Date(shiftedOpenMs)]],
        open: [[open]],
        high: [[high]],
        low: [[low]],
        close: [[close]]
      }, [priceTraceIdx], (MAX_POINTS && MAX_POINTS > 0) ? MAX_POINTS : undefined);
    } catch(e) {}

    tryAutoScroll(lastOpenTimeMs + TZ_SHIFT_MS, barMs);
  }

  function onMessage(ev){
    let msg;
    try { msg = JSON.parse(ev.data); } catch(e) { return; }
    const data = msg.data || msg;
    if(!data || data.e !== 'kline') return;
    const k = data.k;
    if(!k) return;

    const openTime = k.t;
    const closeTime = k.T;
    const isClosed = !!k.x;
    const open = parseFloat(k.o);
    const high = parseFloat(k.h);
    const low = parseFloat(k.l);
    const close = parseFloat(k.c);

    if(!Number.isFinite(openTime) || !Number.isFinite(closeTime)) return;
    if(!Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) return;

    const barMs = Math.max(1, (closeTime - openTime + 1));

    lastOpenTimeMs = openTime;
    lastCloseTimeMs = closeTime;

    lastOpen = open;
    lastHigh = high;
    lastLow = low;

    lastPrice = close;
    lastPriceStr = (typeof k.c === 'string') ? k.c : null;

    if(isClosed){
      appendClosedToHistory(openTime, open, high, low, close, barMs);

      // Move the live candle to the next interval to avoid double-drawing the just-closed bar.
      lastOpenTimeMs = openTime + barMs;
      lastCloseTimeMs = closeTime + barMs;
      lastOpen = close;
      lastHigh = close;
      lastLow = close;
      lastPrice = close;
      lastPriceStr = lastPriceStr;
    }

    // Throttle DOM updates to animation frames
    if(!gd.__tvLiveUpdateScheduled){
      gd.__tvLiveUpdateScheduled = true;
      requestAnimationFrame(function(){
        gd.__tvLiveUpdateScheduled = false;
        updateLiveCandle();
        updateOverlay();
      });
    }
  }

  function connect(){
    if(ws && (ws.readyState === 0 || ws.readyState === 1)) return;
    try {
      ws = new WebSocket(WS_URL);
      ws.onmessage = onMessage;
      ws.onclose = function(){
        ws = null;
        if(reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connect, 1500);
      };
      ws.onerror = function(){
        try { ws.close(); } catch(e) {}
      };
    } catch(e) {}
  }

  // Tick countdown even if price isn't updating
  setInterval(updateOverlay, 1000);
  connect();
})();
"""

def render_plotly_chart(
    fig,
    *,
    tv_axis_scaling: bool,
    realtime_candle: bool,
    symbol: str | None = None,
    timeframe: str | None = None,
    max_points: int | None = None,
    auto_scroll: bool = True,
    height: int | None = None,
) -> None:
    config = {
        "scrollZoom": True,
        "displayModeBar": True,
        "displaylogo": False,
        "responsive": True,
    }
    fig_height = height or int(getattr(fig.layout, "height", 800) or 800)

    if tv_axis_scaling or realtime_candle:
        post_scripts = []
        if tv_axis_scaling:
            post_scripts.append(TV_AXIS_SCALE_POST_SCRIPT)

        if realtime_candle and symbol and timeframe:
            stream_symbol = ccxt_symbol_to_binance_symbol(symbol)
            stream = f"{stream_symbol}@kline_{timeframe}"
            post_scripts.append(
                TV_REALTIME_CANDLE_POST_SCRIPT
                .replace("__STREAM__", stream)
                .replace("__MAX_POINTS__", str(int(max_points) if max_points is not None else 0))
                .replace("__TZ_SHIFT_MS__", str(3 * 60 * 60 * 1000))
                .replace("__AUTO_SCROLL__", "true" if auto_scroll else "false")
            )

        html = pio.to_html(
            fig,
            full_html=False,
            include_plotlyjs="cdn",
            config=config,
            post_script="\n".join(post_scripts) if post_scripts else None,
            default_width="100%",
            default_height=f"{fig_height}px",
        )
        components.html(html, height=fig_height, scrolling=False)
    else:
        st.plotly_chart(fig, use_container_width=True, config=config)

def _config_signature(config: dict) -> str:
    try:
        payload = json.dumps(config or {}, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:
        payload = str(sorted((config or {}).items()))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()

def _normalize_time(value):
    if value is None:
        return None
    try:
        if isinstance(value, pd.Timestamp):
            ts = value
        elif isinstance(value, (int, float)):
            ts = pd.to_datetime(int(value), unit="ms")
        else:
            ts = pd.to_datetime(value)
    except Exception:
        return None
    if isinstance(ts, pd.Timestamp) and ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts

def _to_gmt3(value):
    ts = _normalize_time(value)
    if ts is None:
        return None
    return ts + pd.Timedelta(hours=3)

def _from_gmt3(value):
    ts = _normalize_time(value)
    if ts is None:
        return None
    return ts - pd.Timedelta(hours=3)

def _format_duration(delta: dt.timedelta | None) -> str:
    if delta is None:
        return ""
    total = int(delta.total_seconds())
    if total < 0:
        total = 0
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def _build_backtest(
    trades,
    *,
    candle_df=None,
    start_ts=None,
    end_ts=None,
    initial_balance=0.0,
    size_mode="fixed",
    fixed_notional=0.0,
    percent_equity=100.0,
    leverage=1.0,
    fee_rate=0.0,
    last_close=None,
    close_time=None,
    close_open_at_end=True,
    # Kar Çekimi Parametreleri
    enable_profit_withdrawal=False,
    growth_threshold_pct=30.0,
    withdrawal_rate_pct=20.0,
    use_reserve_on_max_loss=True,
    min_capital_requirement=0.0,
):
    try:
        initial_balance = float(initial_balance)
    except Exception:
        initial_balance = 0.0
    try:
        fixed_notional = float(fixed_notional)
    except Exception:
        fixed_notional = 0.0
    try:
        percent_equity = float(percent_equity)
    except Exception:
        percent_equity = 0.0
    try:
        leverage = float(leverage)
    except Exception:
        leverage = 1.0
    try:
        fee_rate = float(fee_rate)
    except Exception:
        fee_rate = 0.0

    if leverage <= 0:
        leverage = 1.0
    if percent_equity < 0:
        percent_equity = 0.0
    if percent_equity > 100:
        percent_equity = 100.0
    if fee_rate < 0:
        fee_rate = 0.0

    size_mode = (size_mode or "fixed").strip().lower()

    events = []
    for idx, tr in enumerate(trades or []):
        ts = _normalize_time(tr.get("time") if isinstance(tr, dict) else None)
        if ts is None:
            continue
        ttype = str(tr.get("type") if isinstance(tr, dict) else "") or ""
        price = tr.get("price") if isinstance(tr, dict) else None
        size = tr.get("size") if isinstance(tr, dict) else 0.0
        comment = tr.get("comment") if isinstance(tr, dict) else ""
        try:
            price = float(price) if price is not None else None
        except Exception:
            price = None
        try:
            size = float(size) if size is not None else 0.0
        except Exception:
            size = 0.0

        events.append(
            {
                "time": ts,
                "type": ttype,
                "price": price,
                "size": size,
                "comment": comment,
                "idx": idx,
            }
        )

    events.sort(key=lambda e: (e["time"], e["idx"]))

    def _in_range(ts):
        if start_ts is not None and ts < start_ts:
            return False
        if end_ts is not None and ts > end_ts:
            return False
        return True

    def _join_unique(items):
        seen = set()
        out = []
        for item in items:
            if not item:
                continue
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return ", ".join(out)

    exec_rows = []
    trade_rows = []
    open_info = None
    current = None
    equity = initial_balance
    equity_curve = [equity]
    
    # Kar Çekimi State'leri
    base_capital = initial_balance  # Kar çekimi için referans değer
    reserve = 0.0  # Yedek sermaye (çekilen karların toplamı)
    withdrawal_history = []  # Çekim geçmişi
    reserve_injection_count = 0  # MAX_LOSS'ta yedek enjeksiyonu sayısı
    
    # Candle verilerini hazırla (MAE/MFE için)
    candle_data = None
    if candle_df is not None and not candle_df.empty:
        candle_data = candle_df.copy()
        candle_data["ts_norm"] = candle_data["timestamp"].apply(_normalize_time)
    
    def _calc_mae_mfe(entry_time, exit_time, entry_price, is_long, entry_qty):
        """Trade sırasındaki gerçek MAE/MFE'yi candle verilerinden hesapla"""
        if candle_data is None or entry_time is None or exit_time is None:
            return 0.0, 0.0
        
        # Trade süresince olan candle'ları bul
        mask = (candle_data["ts_norm"] >= entry_time) & (candle_data["ts_norm"] <= exit_time)
        trade_candles = candle_data[mask]
        
        if trade_candles.empty:
            return 0.0, 0.0
        
        max_high = trade_candles["high"].max()
        min_low = trade_candles["low"].min()
        
        if is_long:
            # Long: MFE = en yüksek fiyat - entry, MAE = entry - en düşük fiyat
            mfe = (max_high - entry_price) * entry_qty if max_high > entry_price else 0.0
            mae = (entry_price - min_low) * entry_qty if min_low < entry_price else 0.0
        else:
            # Short: MFE = entry - en düşük fiyat, MAE = en yüksek fiyat - entry
            mfe = (entry_price - min_low) * entry_qty if min_low < entry_price else 0.0
            mae = (max_high - entry_price) * entry_qty if max_high > entry_price else 0.0
        
        return mfe, mae

    def _finalize_trade(tr):
        nonlocal equity
        closed_units = tr["closed_units"]
        if closed_units <= 0:
            return
        exit_price = tr["exit_value"] / closed_units if closed_units > 0 else None
        entry_time = tr["entry_time"]
        exit_time = tr["exit_time"]
        duration = None
        if entry_time is not None and exit_time is not None:
            duration = exit_time - entry_time
        net_pnl = tr["raw_pnl"] - tr["fees"]
        pnl_pct = 0.0
        if tr["entry_margin"]:
            pnl_pct = (net_pnl / tr["entry_margin"]) * 100.0
        
        # Kümülatif PnL hesapla
        cumulative_pnl = equity - initial_balance
        
        # Gerçek MAE/MFE hesapla (candle verilerinden)
        real_mfe, real_mae = _calc_mae_mfe(
            entry_time, 
            exit_time, 
            tr["entry_price"], 
            tr["is_long"], 
            tr["entry_qty"]
        )
        
        # MAE/MFE yüzde hesapla
        mfe_pct = (real_mfe / tr["entry_margin"] * 100.0) if tr["entry_margin"] else 0.0
        mae_pct = (real_mae / tr["entry_margin"] * 100.0) if tr["entry_margin"] else 0.0
        
        trade_rows.append(
            {
                "İşlem #": len(trade_rows) + 1,
                "Tip": "Long" if tr["is_long"] else "Short",
                "Tarih/Saat": _to_gmt3(entry_time).strftime("%d %b %Y, %H:%M") if entry_time else "",
                "Sinyal": tr["entry_comment"] or "-",
                "Fiyat": tr["entry_price"],
                "Pozisyon Büyüklüğü": closed_units,
                "Net PnL": net_pnl,
                "Kümülatif PnL": cumulative_pnl,
                "Yükselmiş (USD)": real_mfe,
                "Yükselmiş (%)": mfe_pct,
                "Düşüş (USD)": real_mae,
                "Düşüş (%)": mae_pct,
                "Kâr/Zarar %": pnl_pct,
                "Bakiye": equity, # Mevcut işlem sonrası bakiye
                "_fees": tr["fees"],  # Internal: fees hesaplama için
            }
        )
        equity_curve.append(equity)
        
        # --- KAR ÇEKİMİ KONTROLÜ ---
        nonlocal base_capital, reserve, withdrawal_history
        if enable_profit_withdrawal and equity > 0:
            target_equity = base_capital * (1 + growth_threshold_pct / 100.0)
            
            # Min sermaye kontrolü: Eğer limit varsa ve bakiye altındaysa çekim yapma
            is_capital_sufficient = (min_capital_requirement <= 0) or (equity >= min_capital_requirement)

            if is_capital_sufficient and equity >= target_equity:
                # Büyüme gerçekleşti, kar üzerinden çekim yap
                current_profit = equity - base_capital
                withdrawal_amount = current_profit * (withdrawal_rate_pct / 100.0)
                
                reserve += withdrawal_amount
                equity -= withdrawal_amount
                new_base = equity  # Yeni referans sermaye
                
                withdrawal_history.append({
                    "time": exit_time,
                    "from_equity": equity + withdrawal_amount,
                    "withdrawal": withdrawal_amount,
                    "new_equity": equity,
                    "reserve_total": reserve,
                    "old_base": base_capital,
                    "new_base": new_base,
                })
                
                # Kar Çekimi satırını işlem listesine ekle
                trade_rows.append({
                    "İşlem #": "",
                    "Tip": "KAR ÇEKİMİ", # Özel tip
                    "Tarih/Saat": _to_gmt3(exit_time).strftime("%d %b %Y, %H:%M") if exit_time else "",
                    "Sinyal": f"Yedek: ${reserve:.2f}",
                    "Fiyat": None,
                    "Pozisyon Büyüklüğü": None,
                    "Net PnL": -withdrawal_amount, # Listede düşüş olarak görünsün (fakat istatistikte hariç tutulmalı)
                    "Kümülatif PnL": equity - initial_balance,
                    "Bakiye": equity,
                    "Yükselmiş (USD)": None,
                    "Yükselmiş (%)": None,
                    "Düşüş (USD)": None,
                    "Düşüş (%)": None,
                    "Kâr/Zarar %": None,
                    "_fees": 0.0,
                })
                
                # Exec logu
                _append_exec(exit_time, "WITHDRAWAL", 1.0, withdrawal_amount, f"Kar Çekimi: -${withdrawal_amount:.2f} (Yedek: ${reserve:.2f})")
                
                base_capital = new_base



    def _append_exec(ts, ttype, price, size, comment, extra=None):
        row = {
            "time": _to_gmt3(ts),
            "type": ttype,
            "price": price,
            "size": size,
            "comment": comment,
        }
        if isinstance(extra, dict):
            row.update(extra)
        exec_rows.append(row)

    def _calc_entry_notional():
        if size_mode.startswith("percent"):
            margin = equity * percent_equity / 100.0
        else:
            margin = fixed_notional
        margin = max(0.0, float(margin or 0.0))
        notional = margin * leverage
        return margin, notional

    def _apply_exit(exit_price, exit_units, exit_type, exit_comment, exit_time, add_exec=True):
        nonlocal equity, current
        if current is None:
            return
        if exit_price is None or exit_units <= 0:
            return
        exit_units = min(exit_units, current["remaining_units"])
        if exit_units <= 0:
            return

        entry_price = current["entry_price"]
        if entry_price is None:
            return

        entry_units = current["entry_units"]
        qty = current["entry_qty"] * (exit_units / entry_units) if entry_units else 0.0
        exit_notional = qty * exit_price

        raw_pnl = (exit_price - entry_price) * qty
        if not current["is_long"]:
            raw_pnl = -raw_pnl
        
        # MAE/MFE tracking - bu exit'teki PnL'yi kontrol et
        if raw_pnl > current["max_favorable_excursion"]:
            current["max_favorable_excursion"] = raw_pnl
        if raw_pnl < current["max_adverse_excursion"]:
            current["max_adverse_excursion"] = raw_pnl

        fee = exit_notional * (fee_rate / 100.0)
        current["raw_pnl"] += raw_pnl
        current["fees"] += fee
        current["exit_value"] += exit_price * exit_units
        current["closed_units"] += exit_units
        current["remaining_units"] -= exit_units
        current["exit_types"].append(exit_type)
        if exit_comment:
            current["exit_comments"].append(exit_comment)
        current["exit_time"] = exit_time

        equity += raw_pnl - fee

        if add_exec:
            _append_exec(
                exit_time,
                exit_type,
                exit_price,
                exit_units,
                exit_comment,
                {
                    "notional_usdt": exit_notional,
                    "qty": qty,
                    "fee_usdt": fee,
                    "pnl_usdt": raw_pnl,
                    "equity_after": equity,
                },
            )

        if current["remaining_units"] <= 1e-9:
            _finalize_trade(current)
            
            # --- MAX_LOSS'TA YEDEK SERMAYE ENJEKSİYONU ---
            nonlocal reserve, reserve_injection_count, base_capital
            if (
                use_reserve_on_max_loss 
                and reserve > 0 
                and exit_type == "EXIT_SL" 
                and "Max Loss" in (exit_comment or "")
            ):
                # Yedek sermayeyi ana bakiyeye ekle
                injected = reserve
                equity += injected
                reserve = 0.0
                reserve_injection_count += 1
                base_capital = equity  # Yeni referans sermaye
                
                # Enjeksiyon logunu exec'e ekle
                _append_exec(
                    exit_time,
                    "RESERVE_INJECT",
                    None,
                    None,
                    f"Yedek sermaye enjekte edildi: ${injected:.2f}",
                    {
                        "injected_amount": injected,
                        "new_equity": equity,
                        "injection_count": reserve_injection_count,
                    },
                )
                
                # Yedek Enjeksiyonunu işlem listesine de ekle
                trade_rows.append({
                    "İşlem #": "",
                    "Tip": "YEDEK ENJEKSİYON",
                    "Tarih/Saat": _to_gmt3(exit_time).strftime("%d %b %Y, %H:%M") if exit_time else "",
                    "Sinyal": f"Eklendi: ${injected:.2f}",
                    "Fiyat": None,
                    "Pozisyon Büyüklüğü": None,
                    "Net PnL": injected,
                    "Kümülatif PnL": equity - initial_balance,
                    "Bakiye": equity,
                    "Yükselmiş (USD)": None,
                    "Yükselmiş (%)": None,
                    "Düşüş (USD)": None,
                    "Düşüş (%)": None,
                    "Kâr/Zarar %": None,
                    "_fees": 0.0,
                })
            
            current = None

    for ev in events:
        ts = ev["time"]
        if not _in_range(ts):
            if end_ts is not None and ts > end_ts:
                break
            continue

        ttype = ev["type"]
        if ttype.startswith("ENTRY"):
            is_long = "LONG" in ttype
            entry_units = ev["size"] if ev["size"] > 0 else 1.0
            if current is not None and current["remaining_units"] > 0:
                forced_price = ev["price"] if ev["price"] is not None else current["entry_price"]
                _apply_exit(
                    forced_price,
                    current["remaining_units"],
                    "EXIT_FORCED",
                    "Forced close on new entry",
                    ts,
                    add_exec=True,
                )
                current = None

            entry_price = ev["price"]
            entry_margin, entry_notional = _calc_entry_notional()
            entry_qty = (entry_notional / entry_price) if entry_price else 0.0
            entry_fee = entry_notional * (fee_rate / 100.0)
            entry_equity = equity
            equity -= entry_fee

            current = {
                "entry_time": ts,
                "entry_price": entry_price,
                "entry_units": entry_units,
                "remaining_units": entry_units,
                "entry_comment": ev["comment"],
                "entry_notional": entry_notional,
                "entry_margin": entry_margin,
                "entry_qty": entry_qty,
                "entry_equity": entry_equity,
                "is_long": is_long,
                "exit_types": [],
                "exit_comments": [],
                "exit_time": None,
                "exit_value": 0.0,
                "closed_units": 0.0,
                "raw_pnl": 0.0,
                "fees": entry_fee,
                "max_favorable_excursion": 0.0,
                "max_adverse_excursion": 0.0,
            }
            _append_exec(
                ts,
                ttype,
                entry_price,
                entry_units,
                ev["comment"],
                {
                    "notional_usdt": entry_notional,
                    "qty": entry_qty,
                    "fee_usdt": entry_fee,
                    "equity_after": equity,
                },
            )
            continue

        if ttype.startswith("EXIT"):
            if current is None or current["entry_price"] is None:
                _append_exec(ts, ttype, ev["price"], ev["size"], ev["comment"])
                continue
            if ev["price"] is None or ev["size"] <= 0:
                _append_exec(ts, ttype, ev["price"], ev["size"], ev["comment"])
                continue
            _apply_exit(ev["price"], ev["size"], ttype, ev["comment"], ts, add_exec=True)

    if (
        close_open_at_end
        and current is not None
        and current["remaining_units"] > 0
        and last_close is not None
        and close_time is not None
    ):
        forced_price = float(last_close)
        forced_units = current["remaining_units"]
        _apply_exit(
            forced_price,
            forced_units,
            "EXIT_END",
            "Backtest end",
            close_time,
            add_exec=True,
        )

    if current is not None and current["remaining_units"] > 0:
        open_info = {
            "entry_time": _to_gmt3(current["entry_time"]),
            "side": "LONG" if current["is_long"] else "SHORT",
            "entry_price": current["entry_price"],
            "remaining_units": current["remaining_units"],
            "entry_notional": current["entry_notional"],
            "entry_margin": current["entry_margin"],
            "entry_qty": current["entry_qty"],
        }

    trades_df = pd.DataFrame(trade_rows)
    exec_df = pd.DataFrame(exec_rows)

    # İstatistikler için sadece gerçek işlemleri kullan (Kar Çekimi hariç)
    real_trades = [r for r in trade_rows if r.get("Tip") != "KAR ÇEKİMİ"]

    total_trades = len(real_trades)
    wins = len([r for r in real_trades if r.get("Net PnL", 0) > 0])
    losses = len([r for r in real_trades if r.get("Net PnL", 0) < 0])
    net_profit = equity - initial_balance
    net_profit_pct = (net_profit / initial_balance * 100.0) if initial_balance else 0.0
    gross_profit = sum(r.get("Net PnL", 0) for r in real_trades if r.get("Net PnL", 0) > 0)
    gross_loss = abs(sum(r.get("Net PnL", 0) for r in real_trades if r.get("Net PnL", 0) < 0))
    total_fees = sum(r.get("_fees", 0) for r in real_trades)

    profit_factor = 0.0
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")

    avg_win = (gross_profit / wins) if wins else 0.0
    avg_loss = (-gross_loss / losses) if losses else 0.0
    avg_trade = (net_profit / total_trades) if total_trades else 0.0

    peak = equity_curve[0] if equity_curve else initial_balance
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        drawdown = peak - eq
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            if peak > 0:
                max_drawdown_pct = (drawdown / peak) * 100.0

    summary = {
        "initial_balance": initial_balance,
        "ending_balance": equity,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / total_trades * 100) if total_trades else 0.0,
        "net_profit_usdt": net_profit,
        "net_profit_pct": net_profit_pct,
        "gross_profit_usdt": gross_profit,
        "gross_loss_usdt": gross_loss,
        "profit_factor": profit_factor,
        "avg_win_usdt": avg_win,
        "avg_loss_usdt": avg_loss,
        "avg_trade_usdt": avg_trade,
        "max_drawdown_usdt": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "fees_usdt": total_fees,
        "open_trade": open_info,
        # Kar Çekimi Bilgileri
        "total_withdrawals_usdt": sum(w["withdrawal"] for w in withdrawal_history),
        "withdrawal_count": len(withdrawal_history),
        "final_reserve_usdt": reserve,
        "reserve_injection_count": reserve_injection_count,
        "withdrawal_history": withdrawal_history,
    }

    return summary, trades_df, exec_df, open_info

def _build_backtest_excel(summary, trades_df, exec_df):
    output = BytesIO()
    summary_df = pd.DataFrame([summary])
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        if trades_df is not None:
            trades_df.to_excel(writer, sheet_name="Trades", index=False)
        if exec_df is not None:
            exec_df.to_excel(writer, sheet_name="Executions", index=False)
    output.seek(0)
    return output.getvalue()

def _sync_chart_ws(symbol: str, timeframe: str, enabled: bool) -> None:
    current_key = st.session_state.get("_chart_ws_key")
    stream = st.session_state.get("_chart_ws_stream")
    desired_key = f"{symbol}::{timeframe}"

    def _stop():
        nonlocal stream
        try:
            if stream is not None:
                stream.stop()
        except Exception:
            pass
        stream = None
        st.session_state["_chart_ws_stream"] = None
        st.session_state["_chart_ws_key"] = None

    if not enabled:
        if stream is not None:
            _stop()
        return

    if stream is None or current_key != desired_key:
        _stop()
        stream = BinanceFuturesKlineStream(symbol, timeframe)
        stream.start()
        st.session_state["_chart_ws_stream"] = stream
        st.session_state["_chart_ws_key"] = desired_key

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

def run_live_trading(selected_pairs_tv, timeframe: str, config_overrides: dict) -> None:
    if not live_trading_enabled:
        return

    trade_symbols = [tv_perp_to_ccxt_swap_symbol(p) for p in (selected_pairs_tv or [])]
    trade_symbols = [s for s in trade_symbols if isinstance(s, str) and s.strip()]
    if not trade_symbols:
        return

    engines = st.session_state.setdefault("live_trade_engines", {})
    desired_keys = {f"{symbol}::{timeframe}" for symbol in trade_symbols}
    for key in list(engines.keys()):
        if key not in desired_keys:
            del engines[key]

    status_rows = []
    for symbol in trade_symbols:
        key = f"{symbol}::{timeframe}"
        engine = engines.get(key)

        try:
            if engine is None:
                data_manager = DataManager()
                strategy = YulaStrategy(config_overrides=config_overrides)
                state = YulaState()
                trader = Trader(data_manager.exchange)
                trader.config.LIVE_TRADING = True

                df = data_manager.fetch_initial_data(symbol, timeframe)
                if df.empty:
                    raise RuntimeError("No data fetched for warmup.")

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
                        "volume": row["volume"],
                    }
                    strategy.calculate(candle, state, index)

                state.trades = []
                state.position_size = 0
                state.pendingLongEntry = False
                state.pendingShortEntry = False
                state.pendingEntryBar = None
                state.pendingEntryReason = ""
                strategy._reset_position_state(state)
                trader.reset()

                engine = {
                    "data_manager": data_manager,
                    "strategy": strategy,
                    "state": state,
                    "trader": trader,
                    "last_processed_ts": df["timestamp"].iloc[-1] if not df.empty else None,
                    "next_index": len(df),
                }
                engines[key] = engine

            data_manager = engine["data_manager"]
            strategy = engine["strategy"]
            state = engine["state"]
            trader = engine["trader"]
            trader.config.LIVE_TRADING = True

            latest_closed = data_manager.fetch_latest_candle(symbol, timeframe)
            if latest_closed is None:
                status_rows.append({"pair": symbol, "status": "no data"})
                continue

            latest_closed_ts = latest_closed["timestamp"]
            last_processed_ts = engine.get("last_processed_ts")
            if last_processed_ts is None or latest_closed_ts <= last_processed_ts:
                status_rows.append({"pair": symbol, "status": "up to date"})
                continue

            since_ms = int(pd.Timestamp(last_processed_ts).timestamp() * 1000)
            ohlcv = data_manager.exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=1000)
            if not ohlcv:
                status_rows.append({"pair": symbol, "status": "no updates"})
                continue

            df_new = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df_new["timestamp"] = pd.to_datetime(df_new["timestamp"], unit="ms")
            df_new = df_new[df_new["timestamp"] > last_processed_ts]
            df_new = df_new[df_new["timestamp"] <= latest_closed_ts]
            df_new = df_new.sort_values("timestamp").reset_index(drop=True)

            processed = 0
            for _, row in df_new.iterrows():
                candle = {
                    "timestamp": row["timestamp"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                }
                strategy.calculate(candle, state, engine["next_index"])
                engine["next_index"] += 1
                trader.process_new_trades(state, candle, symbol)
                engine["last_processed_ts"] = candle["timestamp"]
                processed += 1

            status_rows.append({"pair": symbol, "status": f"processed {processed} candle(s)"})

        except Exception as e:
            status_rows.append({"pair": symbol, "status": f"error: {e}"})

    if status_rows:
        with st.sidebar.expander("Live Trading Status", expanded=False):
            st.dataframe(pd.DataFrame(status_rows), use_container_width=True)

@st.cache_data(ttl=60)
def fetch_candles(symbol, timeframe, limit=15000, since_ms=None, until_ms=None):
    try:
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
            }
        })
        try:
            if hasattr(exchange, "load_time_difference"):
                exchange.load_time_difference()
        except Exception:
            pass
        timeframe_duration_seconds = exchange.parse_timeframe(timeframe)
        now_ms = exchange.milliseconds()
        end_ms = int(until_ms) if until_ms is not None else now_ms
        
        # Calculate start time: limit * duration * 1000
        # We want the LAST 'limit' candles.
        # Fetching backwards is tricky with CCXT if we don't know the exact start.
        # But we can estimate start.
        
        all_candles = []
        # Fetch in batches of 1000 (Binance limit)
        # We need to loop.
        # Strategy: Fetch latest 1000. Then take the timestamp of the first one, subtract duration, and fetch 1000 before that.
        
        # If since_ms is provided, fetch forward from that point.
        # Otherwise, fetch the last `limit` candles ending at end_ms.
        if since_ms is not None:
            start_timestamp = int(since_ms)
        else:
            total_duration_ms = int(limit) * timeframe_duration_seconds * 1000
            start_timestamp = end_ms - total_duration_ms
        
        current_since = start_timestamp
        
        while len(all_candles) < limit:
            # We might need to adjust 'since' if we are getting duplicates or gaps, 
            # but standard sequential fetch usually works if we update 'since'.
            # Binance fetch_ohlcv with 'since' returns candles starting from 'since'.
            
            batch = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=1000)
            if not batch:
                break

            if until_ms is not None:
                batch = [c for c in batch if c and c[0] <= end_ms]
                if not batch:
                    break
            
            all_candles.extend(batch)
            if since_ms is not None and len(all_candles) >= limit:
                all_candles = all_candles[: int(limit)]
                break
            
            # Update since to the timestamp of the last candle + 1ms (or duration)
            # actually + duration is safer to avoid overlap if using open time
            last_candle_time = batch[-1][0]
            current_since = last_candle_time + 1
            if last_candle_time >= end_ms:
                break
            
            if len(batch) < 1000:
                # No more data available
                break
                
            # Safety break to prevent infinite loops
            if len(all_candles) > limit + 1000: 
                break
                
        # Trim to exact limit if we got more (from the start side usually, but here we fetched from calculated start)
        if len(all_candles) > limit:
            if since_ms is not None:
                all_candles = all_candles[: int(limit)]
            else:
                # We want the LATEST 'limit' candles.
                all_candles = all_candles[-int(limit):]
            
        df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = df.drop_duplicates(subset=['timestamp'], keep='last').sort_values('timestamp').reset_index(drop=True)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

# Set page config
st.set_page_config(layout="wide", page_title="YULA Bot Dashboard")

st.sidebar.title("YULA Bot Settings")

st.sidebar.subheader("Trading")
live_trading_enabled = st.sidebar.toggle("Enable Live Trading", value=False, key="live_trading_enabled")
selected_trade_pairs_tv = st.sidebar.multiselect(
    "Trade Pairs",
    TRADE_PAIRS_TV,
    default=DEFAULT_TRADE_PAIRS_TV,
    key="selected_trade_pairs_tv",
)
_prev_live_enabled = st.session_state.get("_prev_live_trading_enabled", False)
if live_trading_enabled and not _prev_live_enabled:
    if "live_trade_engines" in st.session_state:
        del st.session_state["live_trade_engines"]
st.session_state["_prev_live_trading_enabled"] = live_trading_enabled

# --- Market Selection ---
st.sidebar.header("Market Selection")

if 'symbols' not in st.session_state:
    st.session_state.symbols = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT",
        "LINK/USDT", "ARB/USDT", "AAVE/USDT", "MAV/USDT",
        "ATA/USDT", "MANTA/USDT", "AR/USDT", "YGG/USDT", "TAO/USDT"
    ]

if st.sidebar.button("Fetch All Binance Futures Pairs"):
    with st.spinner("Fetching markets from Binance..."):
        try:
            exchange = ccxt.binance({'options': {'defaultType': 'future'}})
            markets = exchange.load_markets()
            futures_symbols = [symbol for symbol in markets if '/USDT' in symbol]
            futures_symbols.sort()
            st.session_state.symbols = futures_symbols
            st.success(f"Fetched {len(futures_symbols)} pairs.")
        except Exception as e:
            st.error(f"Error fetching markets: {e}")

symbol = st.sidebar.selectbox("Symbol", st.session_state.symbols, index=0)
timeframe = st.sidebar.selectbox("Timeframe", ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"], index=3)
st.sidebar.header("Chart History")
chart_fetch_all = st.sidebar.toggle("Fetch Maximum History (slow)", value=False, key="chart_fetch_all")
if chart_fetch_all:
    chart_fetch_limit = 500000
    st.sidebar.caption("Max history can be slow on small timeframes.")
else:
    chart_fetch_limit = st.sidebar.number_input(
        "Chart Candle Limit",
        min_value=1000,
        max_value=500000,
        value=15000,
        step=1000,
        key="chart_fetch_limit",
    )

st.sidebar.subheader("Chart Performance")
render_candle_limit = st.sidebar.number_input(
    "Max Display Candles (faster zoom)",
    min_value=500,
    max_value=int(chart_fetch_limit),
    value=min(5000, int(chart_fetch_limit)),
    step=500,
    key="render_candle_limit",
)
tv_axis_scaling = st.sidebar.toggle(
    "TradingView Axis Drag Zoom",
    value=True,
    key="tv_axis_scaling",
)
st.sidebar.caption("Drag right price scale to zoom Y, bottom time scale to zoom X.")
realtime_candle = st.sidebar.toggle(
    "Realtime Candle + Countdown (TradingView)",
    value=True,
    key="realtime_candle",
)
st.sidebar.caption("Shows current candle price + time-to-close.")
auto_scroll_live = st.sidebar.toggle(
    "Auto-scroll (Live)",
    value=True,
    key="auto_scroll_live",
)
use_ws_live = st.sidebar.toggle(
    "Binance WebSocket Live Feed (fast)",
    value=False,
    key="use_ws_live",
)
st.sidebar.caption("Reduces REST polling during Live Data.")

st.sidebar.subheader("History Range")
st.sidebar.caption("Dates are interpreted as UTC+3.")
_chart_tz = dt.timezone(dt.timedelta(hours=3))

chart_since_ms = None
if st.sidebar.toggle("Use Start Date (UTC+3)", value=False, key="chart_use_start"):
    chart_start_date = st.sidebar.date_input(
        "Start Date",
        value=dt.date.today() - dt.timedelta(days=30),
        key="chart_start_date",
    )
    chart_start_time = st.sidebar.time_input(
        "Start Time",
        value=dt.time(0, 0),
        key="chart_start_time",
    )
    chart_since_ms = int(
        dt.datetime.combine(chart_start_date, chart_start_time, tzinfo=_chart_tz)
        .astimezone(dt.timezone.utc)
        .timestamp()
        * 1000
    )

chart_until_ms = None
if st.sidebar.toggle("Use End Date (UTC+3)", value=False, key="chart_use_end"):
    chart_end_date = st.sidebar.date_input(
        "End Date",
        value=dt.date.today(),
        key="chart_end_date",
    )
    chart_end_time = st.sidebar.time_input(
        "End Time",
        value=dt.time(23, 59),
        key="chart_end_time",
    )
    chart_until_ms = int(
        dt.datetime.combine(chart_end_date, chart_end_time, tzinfo=_chart_tz)
        .astimezone(dt.timezone.utc)
        .timestamp()
        * 1000
    )

_ws_enabled = bool(use_ws_live) and bool(st.session_state.get("auto_refresh", False)) and chart_until_ms is None
_sync_chart_ws(symbol, timeframe, _ws_enabled)

if chart_since_ms is not None and chart_until_ms is not None and chart_until_ms < chart_since_ms:
    st.sidebar.error("End Date must be after Start Date.")

if chart_since_ms is not None:
    tf_seconds = {
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "1d": 86400,
    }.get(timeframe, 0)
    if tf_seconds:
        approx_end_ms = int(chart_until_ms) if chart_until_ms is not None else int(time.time() * 1000)
        approx_needed = max(0, approx_end_ms - int(chart_since_ms))
        approx_candles = int(math.ceil(approx_needed / (tf_seconds * 1000))) + 1
        if approx_candles > int(chart_fetch_limit):
            start_dt_utc = dt.datetime.fromtimestamp(int(chart_since_ms) / 1000, tz=dt.timezone.utc)
            covered_end_utc = start_dt_utc + dt.timedelta(seconds=tf_seconds * int(chart_fetch_limit))
            covered_end_local = covered_end_utc.astimezone(_chart_tz)
            st.sidebar.warning(
                f"Selected range needs ~{approx_candles} candles; current limit is {int(chart_fetch_limit)}. "
                f"Chart will stop around {covered_end_local.strftime('%Y-%m-%d %H:%M')} (UTC+3)."
            )

st.sidebar.subheader("Chart Navigation")
st.sidebar.caption("Jump the chart view without refetching data (UTC+3).")
goto_mode = st.sidebar.radio(
    "Go To",
    ["Date", "Range"],
    horizontal=True,
    key="chart_goto_mode",
)

goto_date = None
goto_time = None
goto_start = None
goto_end = None
goto_window = None

if goto_mode == "Date":
    goto_date = st.sidebar.date_input(
        "Go to Date",
        value=dt.date.today(),
        key="chart_goto_date",
    )
    goto_time = st.sidebar.time_input(
        "Go to Time",
        value=dt.time(0, 0),
        key="chart_goto_time",
    )
    goto_window = st.sidebar.number_input(
        "Window (candles)",
        min_value=50,
        max_value=5000,
        value=200,
        step=50,
        key="chart_goto_window",
    )
else:
    goto_start_date = st.sidebar.date_input(
        "Range Start Date",
        value=st.session_state.get("bt_nav_start_date", dt.date.today() - dt.timedelta(days=7)),
        key="chart_goto_range_start_date",
    )
    goto_start_time = st.sidebar.time_input(
        "Range Start Time",
        value=st.session_state.get("bt_nav_start_time", dt.time(0, 0)),
        key="chart_goto_range_start_time",
    )
    goto_end_date = st.sidebar.date_input(
        "Range End Date",
        value=st.session_state.get("bt_nav_end_date", dt.date.today()),
        key="chart_goto_range_end_date",
    )
    goto_end_time = st.sidebar.time_input(
        "Range End Time",
        value=st.session_state.get("bt_nav_end_time", dt.time(23, 59)),
        key="chart_goto_range_end_time",
    )
    goto_start = dt.datetime.combine(goto_start_date, goto_start_time)
    goto_end = dt.datetime.combine(goto_end_date, goto_end_time)
    # Session state'e kaydet (backtest için kullanılabilsin)
    st.session_state["bt_nav_start_date"] = goto_start_date
    st.session_state["bt_nav_start_time"] = goto_start_time
    st.session_state["bt_nav_end_date"] = goto_end_date
    st.session_state["bt_nav_end_time"] = goto_end_time
    st.session_state["bt_nav_start"] = goto_start
    st.session_state["bt_nav_end"] = goto_end

col_goto, col_reset = st.sidebar.columns(2)
if col_goto.button("Go to", key="chart_goto_apply"):
    if goto_mode == "Date":
        target = dt.datetime.combine(goto_date, goto_time)
        st.session_state["chart_goto"] = {
            "mode": "date",
            "target": target,
            "window": int(goto_window) if goto_window else 200,
        }
    else:
        st.session_state["chart_goto"] = {
            "mode": "range",
            "start": goto_start,
            "end": goto_end,
        }
    st.session_state["chart_goto_token"] = str(int(time.time() * 1000))

if col_reset.button("Reset View", key="chart_goto_reset"):
    st.session_state["chart_goto"] = None
    st.session_state["chart_goto_token"] = str(int(time.time() * 1000))

replay_enabled_state = bool(st.session_state.get("replay_enabled", False))
replay_anchor_ts = st.session_state.get("replay_anchor_ts") if replay_enabled_state else None
effective_since_ms = chart_since_ms
effective_until_ms = chart_until_ms
if replay_enabled_state and replay_anchor_ts is not None:
    try:
        tf_seconds = int(ccxt.Exchange.parse_timeframe(timeframe))
    except Exception:
        tf_seconds = {
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "2h": 7200,
            "4h": 14400,
            "1d": 86400,
        }.get(timeframe, 0)
    anchor_utc = _from_gmt3(replay_anchor_ts)
    if anchor_utc is not None and tf_seconds:
        anchor_ms = int(pd.to_datetime(anchor_utc).timestamp() * 1000)
        effective_until_ms = anchor_ms
        effective_since_ms = max(0, anchor_ms - int(chart_fetch_limit) * tf_seconds * 1000)

cache_key = f"{DATA_CACHE_VERSION}:{symbol}_{timeframe}_{int(chart_fetch_limit)}_{effective_since_ms or 'none'}_{effective_until_ms or 'none'}"
if st.session_state.get("_replay_cache_key") != cache_key:
    st.session_state["_replay_cache_key"] = cache_key
    st.session_state["replay_index"] = None
    st.session_state["replay_playing"] = False

st.sidebar.subheader("Replay")
st.sidebar.caption("Replay candles up to a chosen point (UTC+3).")
replay_enabled = st.sidebar.toggle("Enable Replay", value=False, key="replay_enabled")
if replay_enabled:
    # Initialize replay_selecting state if not exists
    if "replay_selecting" not in st.session_state:
        st.session_state["replay_selecting"] = False
    
    # Replay point selection button
    col_select, col_clear = st.sidebar.columns(2)
    with col_select:
        if st.button("📍 Bölge Seç", key="replay_select_btn", 
                     type="primary" if st.session_state.get("replay_selecting", False) else "secondary"):
            st.session_state["replay_selecting"] = not st.session_state.get("replay_selecting", False)
    with col_clear:
        if st.button("🔄 Sıfırla", key="replay_reset_btn"):
            st.session_state["replay_index"] = None
            st.session_state["replay_anchor_ts"] = None
            st.session_state["replay_selecting"] = False
            st.session_state["replay_playing"] = False
    
    if st.session_state.get("replay_selecting", False):
        st.sidebar.info("👆 Grafikte başlangıç noktasını seçin")
    
    st.sidebar.markdown("---")
    
    # Replay speed control
    replay_speed_val = st.sidebar.slider(
        "Replay Speed (candles/sec)",
        min_value=0.5,
        max_value=20.0,
        value=5.0,
        step=0.5,
        key="replay_speed_slider",
    )
    
    # Step size control
    replay_step_val = st.sidebar.number_input(
        "Step Size (candles)",
        min_value=1,
        max_value=10,
        value=1,
        step=1,
        key="replay_step_input",
    )
    
    # Play/Pause toggle with clear visual feedback
    col_play, col_step = st.sidebar.columns(2)
    with col_play:
        st.toggle(
            "▶ Play" if not st.session_state.get("replay_playing", False) else "⏸ Pause",
            value=bool(st.session_state.get("replay_playing", False)),
            key="replay_playing",
        )
    with col_step:
        if st.button("⏭ Step", key="replay_step_btn"):
            current_idx = st.session_state.get("replay_index", 0)
            st.session_state["replay_index"] = current_idx + int(replay_step_val)

st.sidebar.subheader("Backtest")
st.sidebar.caption("Backtest range uses UTC+3.")
backtest_use_nav_range = st.sidebar.toggle("Use Navigation Range", value=False, key="bt_use_nav_range")
backtest_use_chart_range = st.sidebar.toggle("Use Chart Range", value=True, key="bt_use_chart_range", disabled=backtest_use_nav_range)
backtest_close_end = st.sidebar.toggle("Close Open Position At End", value=True, key="bt_close_end")
backtest_show_exec = st.sidebar.toggle("Show Execution List", value=False, key="bt_show_exec")

cfg_backtest = Config()
bt_initial_balance = st.sidebar.number_input(
    "Initial Balance (USDT)",
    min_value=0.0,
    value=1000.0,
    step=100.0,
    key="bt_initial_balance",
)
bt_size_label = st.sidebar.selectbox(
    "Order Size Mode",
    ["Percent of Equity (compounding)", "Fixed Notional (USDT)"],
    index=0,
    key="bt_size_mode",
)
bt_size_mode = "percent" if bt_size_label.startswith("Percent") else "fixed"

bt_percent_equity = None
bt_fixed_notional = None
if bt_size_mode == "percent":
    bt_percent_equity = st.sidebar.number_input(
        "Percent of Equity",
        min_value=1.0,
        max_value=100.0,
        value=100.0,
        step=1.0,
        key="bt_percent_equity",
    )
else:
    bt_fixed_notional = st.sidebar.number_input(
        "Order Notional (USDT)",
        min_value=0.0,
        value=float(getattr(cfg_backtest, "ORDER_NOTIONAL_USDT", 0.0)),
        step=10.0,
        key="bt_fixed_notional",
    )

bt_leverage = st.sidebar.number_input(
    "Backtest Leverage",
    min_value=1.0,
    value=float(getattr(cfg_backtest, "LEVERAGE", 1.0)),
    step=1.0,
    key="bt_leverage",
)
bt_fee_rate = st.sidebar.number_input(
    "Fee (%) per side",
    min_value=0.0,
    value=0.0,
    step=0.01,
    key="bt_fee_rate",
)


# --- Strategy Settings ---
st.sidebar.subheader("⚙️ Strateji Ayarları")
bt_enable_cd_threshold = st.sidebar.toggle(
    "C/D Threshold (C/D Filtresi)",
    value=False,
    key="bt_enable_cd_threshold",
    help="Trend değişim sinyallerinde (C/D) yüzde eşiği kullanır"
)
if bt_enable_cd_threshold:
    bt_cd_threshold_pct = st.sidebar.number_input(
        "Threshold (%)",
        min_value=0.1,
        max_value=10.0,
        value=1.0,
        step=0.1,
        key="bt_cd_threshold_pct",
        help="Sinyal için gerekli minimum kırılım yüzdesi"
    )
else:
    bt_cd_threshold_pct = 1.0

# --- Kar Çekimi ve Yedek Sermaye Sistemi ---
st.sidebar.markdown("---")
st.sidebar.subheader("💰 Kar Çekimi Sistemi")
bt_enable_profit_withdrawal = st.sidebar.toggle(
    "Kar Çekimi Aktif",
    value=False,
    key="bt_enable_profit_withdrawal",
    help="Sermaye belirli bir yüzde büyüdüğünde otomatik kar çekimi yapar"
)

if bt_enable_profit_withdrawal:
    bt_growth_threshold = st.sidebar.number_input(
        "Büyüme Eşiği (%)",
        min_value=1.0,
        max_value=500.0,
        value=30.0,
        step=5.0,
        key="bt_growth_threshold",
        help="Sermaye bu yüzde kadar büyüdüğünde kar çekimi yapılır"
    )
    bt_withdrawal_rate = st.sidebar.number_input(
        "Çekim Oranı (%)",
        min_value=1.0,
        max_value=100.0,
        value=20.0,
        step=5.0,
        key="bt_withdrawal_rate",
        help="Büyüme gerçekleştiğinde mevcut bakiyenin bu yüzdesi çekilir"
    )
    bt_min_withdr_capital = st.sidebar.number_input(
        "Min. Sermaye Limiti ($)",
        min_value=0.0,
        value=0.0,
        step=100.0,
        key="bt_min_withdr_capital",
        help="Sermaye bu değerin altındaysa kar çekimi yapılmaz (0 = Devre Dışı)"
    )
    bt_use_reserve_on_max_loss = st.sidebar.toggle(
        "MAX_LOSS'ta Yedek Kullan",
        value=True,
        key="bt_use_reserve_on_max_loss",
        help="MAX_LOSS tetiklendiğinde yedek sermaye ana bakiyeye eklenir"
    )
    
    # Özet bilgi
    st.sidebar.caption(
        f"📊 Sermaye %{bt_growth_threshold:.0f} büyüdüğünde %{bt_withdrawal_rate:.0f} çekilir"
    )
else:
    bt_growth_threshold = 30.0
    bt_withdrawal_rate = 20.0
    bt_min_withdr_capital = 0.0
    bt_use_reserve_on_max_loss = True

st.sidebar.markdown("---")

bt_since_ms = None
bt_until_ms = None

# Session state'ten Navigation Range değerlerini al
nav_start = st.session_state.get("bt_nav_start")
nav_end = st.session_state.get("bt_nav_end")

# Öncelik: Navigation Range > Chart Range > Manual Date
if backtest_use_nav_range and nav_start is not None and nav_end is not None:
    # Navigation Range'den al (session state'ten)
    bt_since_ms = int(
        nav_start.replace(tzinfo=_chart_tz)
        .astimezone(dt.timezone.utc)
        .timestamp()
        * 1000
    )
    bt_until_ms = int(
        nav_end.replace(tzinfo=_chart_tz)
        .astimezone(dt.timezone.utc)
        .timestamp()
        * 1000
    )
    st.sidebar.info(f"📅 Backtest Range: {nav_start.strftime('%Y-%m-%d %H:%M')} → {nav_end.strftime('%Y-%m-%d %H:%M')}")
elif backtest_use_nav_range:
    st.sidebar.warning("⚠️ Navigation Range seçmek için Chart Navigation'da 'Range' modunu seç ve tarih gir.")
elif backtest_use_chart_range:
    bt_since_ms = chart_since_ms
    bt_until_ms = chart_until_ms
else:
    if st.sidebar.toggle("Use Start Date (UTC+3)", value=False, key="bt_use_start"):
        bt_start_date = st.sidebar.date_input(
            "Backtest Start Date",
            value=dt.date.today() - dt.timedelta(days=30),
            key="bt_start_date",
        )
        bt_start_time = st.sidebar.time_input(
            "Backtest Start Time",
            value=dt.time(0, 0),
            key="bt_start_time",
        )
        bt_since_ms = int(
            dt.datetime.combine(bt_start_date, bt_start_time, tzinfo=_chart_tz)
            .astimezone(dt.timezone.utc)
            .timestamp()
            * 1000
        )

    if st.sidebar.toggle("Use End Date (UTC+3)", value=False, key="bt_use_end"):
        bt_end_date = st.sidebar.date_input(
            "Backtest End Date",
            value=dt.date.today(),
            key="bt_end_date",
        )
        bt_end_time = st.sidebar.time_input(
            "Backtest End Time",
            value=dt.time(23, 59),
            key="bt_end_time",
        )
        bt_until_ms = int(
            dt.datetime.combine(bt_end_date, bt_end_time, tzinfo=_chart_tz)
            .astimezone(dt.timezone.utc)
            .timestamp()
            * 1000
        )

if bt_since_ms is not None and bt_until_ms is not None and bt_until_ms < bt_since_ms:
    st.sidebar.error("Backtest End Date must be after Start Date.")

# --- Strategy Settings ---
st.sidebar.header("Strategy Configuration")

# 1. Momentum Filter Settings
with st.sidebar.expander("Momentum Filter Settings", expanded=False):
    enable_momentum = st.checkbox("Enable Momentum Filter", value=Config.ENABLE_MOMENTUM_FILTER)
    momentum_multiplier = st.number_input("Momentum Multiplier", value=Config.MOMENTUM_MULTIPLIER, step=0.1)
    show_momentum_info = st.checkbox("Show Momentum Info Panel", value=Config.SHOW_MOMENTUM_INFO)
    enable_momentum_break = st.checkbox("Enable Range Break Filter for Momentum", value=Config.ENABLE_MOMENTUM_RANGE_BREAK_FILTER)

# 2. Momentum Tolerance Settings
with st.sidebar.expander("Momentum Tolerance Settings", expanded=False):
    momentum_tolerance = st.number_input("Momentum Seviye Toleransı (%)", value=Config.MOMENTUM_TOLERANCE_PERCENT, step=1.0)
    enable_momentum_tolerance = st.checkbox("Momentum Tolerans Kontrolünü Aktifleştir", value=Config.ENABLE_MOMENTUM_TOLERANCE)

# 3. Advanced TP System
with st.sidebar.expander("Advanced TP System", expanded=False):
    enable_advanced_tp = st.checkbox("Enable Advanced TP System", value=Config.ENABLE_ADVANCED_TP)
    tp1_percent = st.number_input("First TP (%)", value=Config.FIRST_TP_PERCENT, step=0.1)
    tp1_qty = st.number_input("First TP Quantity (%)", value=Config.FIRST_TP_QUANTITY, step=1.0)
    tp2_percent = st.number_input("Second TP (%)", value=Config.SECOND_TP_PERCENT, step=0.1)
    enable_breakeven = st.checkbox("Enable Breakeven After First TP", value=Config.ENABLE_BREAKEVEN_AFTER_FIRST_TP)

# 4. Range Trailing Stop
with st.sidebar.expander("Range Trailing Stop", expanded=False):
    enable_range_trail = st.checkbox("Enable Range-Based Trailing Stop", value=Config.ENABLE_RANGE_TRAILING_STOP)
    range_trail_act = st.number_input("Range Trailing Activation (%)", value=Config.RANGE_TRAILING_ACTIVATION, step=0.5)

# 5. Trailing Profit Stop
with st.sidebar.expander("Trailing Profit Stop", expanded=False):
    enable_profit_trail = st.checkbox("Enable Trailing Profit Stop", value=Config.ENABLE_TRAILING_PROFIT_STOP)
    trail_loss_1 = st.number_input("Loss Threshold 1 (%)", value=Config.TRAILING_PROFIT_LOSS_THRESHOLD_1)
    trail_take_1 = st.number_input("Profit Take Level 1 (%)", value=Config.TRAILING_PROFIT_TAKE_LEVEL_1)
    trail_loss_2 = st.number_input("Loss Threshold 2 (%)", value=Config.TRAILING_PROFIT_LOSS_THRESHOLD_2)
    trail_take_2 = st.number_input("Profit Take Level 2 (%)", value=Config.TRAILING_PROFIT_TAKE_LEVEL_2)
    trail_loss_3 = st.number_input("Loss Threshold 3 (%)", value=Config.TRAILING_PROFIT_LOSS_THRESHOLD_3)
    trail_take_3 = st.number_input("Profit Take Level 3 (%)", value=Config.TRAILING_PROFIT_TAKE_LEVEL_3)

# 6. General Settings
with st.sidebar.expander("General Settings", expanded=False):
    max_line_length = st.number_input("Maximum Line Length", value=Config.MAX_LINE_LENGTH)
    min_bars_xy = st.number_input("Min Bars Between Touch 2 and 3 for X-Y", value=Config.MIN_BARS_BETWEEN_TOUCH_2_3_XY)
    min_bars_ls = st.number_input("Min Bars Between Touch 2 and 3 for L-S", value=Config.MIN_BARS_BETWEEN_TOUCH_2_3_LS)
    min_bars_mn = st.number_input("Min Bars Between Touch 2 and 3 for M-N", value=Config.MIN_BARS_BETWEEN_TOUCH_2_3_MN)

# 7. Day Filter Settings
with st.sidebar.expander("Day Filter Settings", expanded=False):
    enable_day_filter = st.checkbox("Enable Day Filter", value=Config.ENABLE_DAY_FILTER)
    trade_mon = st.checkbox("Trade on Monday", value=Config.TRADE_ON_MONDAY)
    trade_tue = st.checkbox("Trade on Tuesday", value=Config.TRADE_ON_TUESDAY)
    trade_wed = st.checkbox("Trade on Wednesday", value=Config.TRADE_ON_WEDNESDAY)
    trade_thu = st.checkbox("Trade on Thursday", value=Config.TRADE_ON_THURSDAY)
    trade_fri = st.checkbox("Trade on Friday", value=Config.TRADE_ON_FRIDAY)
    trade_sat = st.checkbox("Trade on Saturday", value=Config.TRADE_ON_SATURDAY)
    trade_sun = st.checkbox("Trade on Sunday", value=Config.TRADE_ON_SUNDAY)

# 8. Month Filter Settings
with st.sidebar.expander("Month Filter Settings", expanded=False):
    enable_month_filter = st.checkbox("Enable Month Filter", value=Config.ENABLE_MONTH_FILTER)
    # Compact month selection
    months = ["January", "February", "March", "April", "May", "June", 
              "July", "August", "September", "October", "November", "December"]
    default_months = [m for m in months if getattr(Config, f"TRADE_IN_{m.upper()}", True)]
    selected_months = st.multiselect("Trade in Months", months, default=default_months)
    # Map back to config booleans
    trade_months = {m: (m in selected_months) for m in months}

# 9. Forbidden Hours (Yasaklı Saatler)
with st.sidebar.expander("Yasaklı Saatler", expanded=False):
    enable_forbidden = st.checkbox("Yasaklı Saatler Filtresi", value=Config.ENABLE_FORBIDDEN_HOURS)
    col1, col2 = st.columns(2)
    with col1:
        forbidden_start_h = st.number_input("Yasaklı Başlangıç Saati", 0, 23, Config.FORBIDDEN_START_HOUR)
        forbidden_start_m = st.number_input("Yasaklı Başlangıç Dakikası", 0, 59, Config.FORBIDDEN_START_MINUTE)
    with col2:
        forbidden_end_h = st.number_input("Yasaklı Bitiş Saati", 0, 23, Config.FORBIDDEN_END_HOUR)
        forbidden_end_m = st.number_input("Yasaklı Bitiş Dakikası", 0, 59, Config.FORBIDDEN_END_MINUTE)

# 10. Strategy Settings (Fibs)
with st.sidebar.expander("Strategy Settings", expanded=False):
    x_fib = st.selectbox("X-Fibonacci Level for Long Entry", [0.382, 0.5, 0.618, 0.705], index=2)
    y_fib = st.selectbox("Y-Fibonacci Level for Short Entry", [0.382, 0.5, 0.618, 0.705], index=2)

# 11. Pending Entry
with st.sidebar.expander("Pending Entry", expanded=False):
    enable_pending = st.checkbox("Enable Pending Entry System", value=Config.ENABLE_PENDING_ENTRY)

# 12. Risk Management
with st.sidebar.expander("Risk Management", expanded=False):
    enable_max_loss = st.checkbox("Enable Max Loss Protection", value=Config.ENABLE_MAX_LOSS_PROTECTION, help="Aktif edilirse, Max Loss (%) seviyesinde işlem kapatılır.")
    max_loss_pct = st.number_input("Max Loss (%)", value=Config.MAX_LOSS_PERCENTAGE, min_value=0.1, max_value=100.0, step=0.5, help="Pozisyon bu yüzde kadar zararda olduğunda otomatik kapanır", key="max_loss_pct_input")

# 13. Visualization Settings
with st.sidebar.expander("Visualization Settings", expanded=False):
    show_xy_ranges = st.checkbox("Show X-Y Ranges", value=Config.SHOW_XY_RANGES)
    show_xy_fibs = st.checkbox("Show X-Y Fibonacci Levels", value=Config.SHOW_XY_FIBS)
    show_ls_ranges = st.checkbox("Show L-S Ranges", value=Config.SHOW_LS_RANGES)
    show_ls_fibs = st.checkbox("Show L-S Fibonacci Levels", value=Config.SHOW_LS_FIBS)
    show_mn_ranges = st.checkbox("Show M-N Ranges", value=Config.SHOW_MN_RANGES)
    show_mn_fibs = st.checkbox("Show M-N Fibonacci Levels", value=Config.SHOW_MN_FIBS)
    show_status = st.checkbox("Show Status Panel", value=Config.SHOW_STATUS_PANEL)
    use_old_labels = st.checkbox("Use Old Condition Labels", value=Config.USE_OLD_CONDITION_LABELS)

# 14. Label Settings
with st.sidebar.expander("Label Settings", expanded=False):
    show_x_lbl = st.checkbox("Show X Labels", value=Config.SHOW_X_LABELS)
    show_y_lbl = st.checkbox("Show Y Labels", value=Config.SHOW_Y_LABELS)
    show_l_lbl = st.checkbox("Show L Labels", value=Config.SHOW_L_LABELS)
    show_s_lbl = st.checkbox("Show S Labels", value=Config.SHOW_S_LABELS)
    show_m_lbl = st.checkbox("Show M Labels", value=Config.SHOW_M_LABELS)
    show_n_lbl = st.checkbox("Show N Labels", value=Config.SHOW_N_LABELS)
    show_cond_lbl = st.checkbox("Show Condition Labels", value=Config.SHOW_CONDITION_LABELS)

# 15. Detailed Touch Settings (Grouped by Range)
st.sidebar.markdown("---")
st.sidebar.header("Detailed Touch Settings")

# Helper for Band Options
band_opts = ["upper", "lower"]
comp_opts = ["touch1"]
should_opts = ["above", "below"]

# Long Touch (X)
with st.sidebar.expander("Long Touch (X Range)", expanded=False):
    st.caption("Long Touch 1")
    x1_band = st.selectbox("X1 Band", band_opts, index=1, key="x1b") # lower
    
    st.caption("Long Touch 2")
    x2_band = st.selectbox("X2 Band", band_opts, index=0, key="x2b") # upper
    x2_comp = st.selectbox("X2 Compare With", comp_opts, index=0, key="x2c")
    x2_should = st.selectbox("X2 Should Be", should_opts, index=0, key="x2s") # above
    x2_dist = st.number_input("X2 Min % Dist", value=5.0, key="x2d")
    
    st.caption("Long Touch 3")
    x3_dist = st.number_input("X3 Min % Dist Below X2", value=1.0, key="x3d")

# Short Touch (Y)
with st.sidebar.expander("Short Touch (Y Range)", expanded=False):
    st.caption("Short Touch 1")
    y1_band = st.selectbox("Y1 Band", band_opts, index=0, key="y1b") # upper
    
    st.caption("Short Touch 2")
    y2_band = st.selectbox("Y2 Band", band_opts, index=1, key="y2b") # lower
    y2_comp = st.selectbox("Y2 Compare With", comp_opts, index=0, key="y2c")
    y2_should = st.selectbox("Y2 Should Be", should_opts, index=1, key="y2s") # below
    y2_dist = st.number_input("Y2 Min % Dist", value=5.0, key="y2d")
    
    st.caption("Short Touch 3")
    y3_dist = st.number_input("Y3 Min % Dist Above Y2", value=1.0, key="y3d")

# L Touch
with st.sidebar.expander("L Touch (Long Momentum)", expanded=False):
    st.caption("L Touch 1")
    l1_band = st.selectbox("L1 Band", band_opts, index=1, key="l1b") # lower
    
    st.caption("L Touch 2")
    l2_band = st.selectbox("L2 Band", band_opts, index=0, key="l2b") # upper
    l2_comp = st.selectbox("L2 Compare With", comp_opts, index=0, key="l2c")
    l2_should = st.selectbox("L2 Should Be", should_opts, index=0, key="l2s") # above
    l2_dist = st.number_input("L2 Min % Dist", value=10.0, key="l2d")
    
    st.caption("L Touch 3")
    l3_dist = st.number_input("L3 Min % Dist Below L2", value=5.0, key="l3d")

# S Touch
with st.sidebar.expander("S Touch (Short Momentum)", expanded=False):
    st.caption("S Touch 1")
    s1_band = st.selectbox("S1 Band", band_opts, index=0, key="s1b") # upper
    
    st.caption("S Touch 2")
    s2_band = st.selectbox("S2 Band", band_opts, index=1, key="s2b") # lower
    s2_comp = st.selectbox("S2 Compare With", comp_opts, index=0, key="s2c")
    s2_should = st.selectbox("S2 Should Be", should_opts, index=1, key="s2s") # below
    s2_dist = st.number_input("S2 Min % Dist", value=10.0, key="s2d")
    
    st.caption("S Touch 3")
    s3_dist = st.number_input("S3 Min % Dist Above S2", value=5.0, key="s3d")

# M Touch
with st.sidebar.expander("M Touch", expanded=False):
    st.caption("M Touch 1")
    m1_band = st.selectbox("M1 Band", band_opts, index=1, key="m1b") # lower
    
    st.caption("M Touch 2")
    m2_band = st.selectbox("M2 Band", band_opts, index=0, key="m2b") # upper
    m2_comp = st.selectbox("M2 Compare With", comp_opts, index=0, key="m2c")
    m2_should = st.selectbox("M2 Should Be", should_opts, index=0, key="m2s") # above
    m2_dist = st.number_input("M2 Min % Dist", value=0.1, key="m2d")
    
    st.caption("M Touch 3")
    m3_dist = st.number_input("M3 Min % Dist Below M2", value=0.1, key="m3d")

# N Touch
with st.sidebar.expander("N Touch", expanded=False):
    st.caption("N Touch 1")
    n1_band = st.selectbox("N1 Band", band_opts, index=0, key="n1b") # upper
    
    st.caption("N Touch 2")
    n2_band = st.selectbox("N2 Band", band_opts, index=1, key="n2b") # lower
    n2_comp = st.selectbox("N2 Compare With", comp_opts, index=0, key="n2c")
    n2_should = st.selectbox("N2 Should Be", should_opts, index=1, key="n2s") # below
    n2_dist = st.number_input("N2 Min % Dist", value=0.1, key="n2d")
    
    st.caption("N Touch 3")
    n3_dist = st.number_input("N3 Min % Dist Above N2", value=0.1, key="n3d")


# --- Execution ---
# --- Execution ---

# Auto-Refresh Settings
st.sidebar.markdown("---")
st.sidebar.header("Live Update Settings")
auto_refresh = st.sidebar.checkbox("🔴 Canlı Veri (Live Data)", value=False, key='auto_refresh')
refresh_rate = st.sidebar.slider("Refresh Rate (seconds)", 1, 60, 5)
if replay_enabled and auto_refresh:
    st.sidebar.warning("Auto-refresh disabled while Replay is enabled.")
    auto_refresh = False
if chart_until_ms is not None:
    if auto_refresh:
        st.sidebar.warning("Auto-refresh disabled when End Date is set.")
    auto_refresh = False

with st.spinner("Calculating strategy..."):
    # Lock strategy settings to the requested TradingView screenshots (fixed/immutable).
    # enable_momentum = True
    # momentum_multiplier = 1.0
    # show_momentum_info = False
    # enable_momentum_break = False

    # momentum_tolerance = 15.0
    # enable_momentum_tolerance = True

    # enable_advanced_tp = True
    # tp1_percent = 5.0
    # tp1_qty = 20.0
    # tp2_percent = 99.0
    # enable_breakeven = True

    # enable_range_trail = True
    # range_trail_act = 10.0

    # enable_profit_trail = True
    # trail_loss_1 = 10.0
    # trail_take_1 = 0.1
    # trail_loss_2 = 99.0
    # trail_take_2 = 1.0
    # trail_loss_3 = 99.0
    # trail_take_3 = 3.0

    # max_line_length = 9999999
    # min_bars_xy = 1
    # min_bars_ls = 1
    # min_bars_mn = 1

    # enable_day_filter = False
    # trade_mon = trade_tue = trade_wed = trade_thu = trade_fri = trade_sat = trade_sun = False

    # enable_month_filter = False
    # trade_months = {m: True for m in months}

    # enable_pending = True
    # # max_loss_pct kullanıcı tarafından sidebar'dan girilir, override etmiyoruz

    # x1_band = "lower"
    # x2_band = "upper"
    # x2_comp = "touch1"
    # x2_should = "above"
    # x2_dist = 5.0
    # x3_dist = 1.0

    # y1_band = "upper"
    # y2_band = "lower"
    # y2_comp = "touch1"
    # y2_should = "below"
    # y2_dist = 5.0
    # y3_dist = 1.0

    # l1_band = "lower"
    # l2_band = "upper"
    # l2_comp = "touch1"
    # l2_should = "above"
    # l2_dist = 10.0
    # l3_dist = 5.0

    # s1_band = "upper"
    # s2_band = "lower"
    # s2_comp = "touch1"
    # s2_should = "below"
    # s2_dist = 10.0
    # s3_dist = 5.0

    # m1_band = "lower"
    # m2_band = "upper"
    # m2_comp = "touch1"
    # m2_should = "above"
    # m2_dist = 0.1
    # m3_dist = 0.1

    # n1_band = "upper"
    # n2_band = "lower"
    # n2_comp = "touch1"
    # n2_should = "below"
    # n2_dist = 0.1
    # n3_dist = 0.1

    # Config Overrides
    config_overrides = {
        # Momentum
        'ENABLE_MOMENTUM_FILTER': enable_momentum,
        'MOMENTUM_MULTIPLIER': momentum_multiplier,
        'SHOW_MOMENTUM_INFO': show_momentum_info,
        'ENABLE_MOMENTUM_RANGE_BREAK_FILTER': enable_momentum_break,
        'MOMENTUM_TOLERANCE_PERCENT': momentum_tolerance,
        'ENABLE_MOMENTUM_TOLERANCE': enable_momentum_tolerance,
        
        # TP & Trail
        'ENABLE_ADVANCED_TP': enable_advanced_tp,
        'FIRST_TP_PERCENT': tp1_percent,
        'FIRST_TP_QUANTITY': tp1_qty,
        'SECOND_TP_PERCENT': tp2_percent,
        'ENABLE_BREAKEVEN_AFTER_FIRST_TP': enable_breakeven,
        'ENABLE_RANGE_TRAILING_STOP': enable_range_trail,
        'RANGE_TRAILING_ACTIVATION': range_trail_act,
        'ENABLE_TRAILING_PROFIT_STOP': enable_profit_trail,
        'TRAILING_PROFIT_LOSS_THRESHOLD_1': trail_loss_1,
        'TRAILING_PROFIT_TAKE_LEVEL_1': trail_take_1,
        'TRAILING_PROFIT_LOSS_THRESHOLD_2': trail_loss_2,
        'TRAILING_PROFIT_TAKE_LEVEL_2': trail_take_2,
        'TRAILING_PROFIT_LOSS_THRESHOLD_3': trail_loss_3,
        'TRAILING_PROFIT_TAKE_LEVEL_3': trail_take_3,
        
        # General
        'MAX_LINE_LENGTH': max_line_length,
        'MIN_BARS_BETWEEN_TOUCH_2_3_XY': min_bars_xy,
        'MIN_BARS_BETWEEN_TOUCH_2_3_LS': min_bars_ls,
        'MIN_BARS_BETWEEN_TOUCH_2_3_MN': min_bars_mn,
        
        # Filters
        'ENABLE_DAY_FILTER': enable_day_filter,
        'TRADE_ON_MONDAY': trade_mon,
        'TRADE_ON_TUESDAY': trade_tue,
        'TRADE_ON_WEDNESDAY': trade_wed,
        'TRADE_ON_THURSDAY': trade_thu,
        'TRADE_ON_FRIDAY': trade_fri,
        'TRADE_ON_SATURDAY': trade_sat,
        'TRADE_ON_SUNDAY': trade_sun,
        
        'ENABLE_MONTH_FILTER': enable_month_filter,
        'TRADE_IN_JANUARY': trade_months["January"],
        'TRADE_IN_FEBRUARY': trade_months["February"],
        'TRADE_IN_MARCH': trade_months["March"],
        'TRADE_IN_APRIL': trade_months["April"],
        'TRADE_IN_MAY': trade_months["May"],
        'TRADE_IN_JUNE': trade_months["June"],
        'TRADE_IN_JULY': trade_months["July"],
        'TRADE_IN_AUGUST': trade_months["August"],
        'TRADE_IN_SEPTEMBER': trade_months["September"],
        'TRADE_IN_OCTOBER': trade_months["October"],
        'TRADE_IN_NOVEMBER': trade_months["November"],
        'TRADE_IN_DECEMBER': trade_months["December"],
        
        'ENABLE_FORBIDDEN_HOURS': enable_forbidden,
        'FORBIDDEN_START_HOUR': forbidden_start_h,
        'FORBIDDEN_START_MINUTE': forbidden_start_m,
        'FORBIDDEN_END_HOUR': forbidden_end_h,
        'FORBIDDEN_END_MINUTE': forbidden_end_m,
        
        # Strategy
        'X_FIB_LEVEL_CHOICE': x_fib,
        'Y_FIB_LEVEL_CHOICE': y_fib,
        'ENABLE_PENDING_ENTRY': enable_pending,
        'MAX_LOSS_PERCENTAGE': max_loss_pct,
        'ENABLE_MAX_LOSS_PROTECTION': enable_max_loss,
        'ENABLE_CD_THRESHOLD': bt_enable_cd_threshold,
        'CD_THRESHOLD_PERCENT': bt_cd_threshold_pct,
        
        # Visualization
        'SHOW_XY_RANGES': show_xy_ranges,
        'SHOW_XY_FIBS': show_xy_fibs,
        'SHOW_LS_RANGES': show_ls_ranges,
        'SHOW_LS_FIBS': show_ls_fibs,
        'SHOW_MN_RANGES': show_mn_ranges,
        'SHOW_MN_FIBS': show_mn_fibs,
        'SHOW_STATUS_PANEL': show_status,
        'USE_OLD_CONDITION_LABELS': use_old_labels,
        
        'SHOW_X_LABELS': show_x_lbl,
        'SHOW_Y_LABELS': show_y_lbl,
        'SHOW_L_LABELS': show_l_lbl,
        'SHOW_S_LABELS': show_s_lbl,
        'SHOW_M_LABELS': show_m_lbl,
        'SHOW_N_LABELS': show_n_lbl,
        'SHOW_CONDITION_LABELS': show_cond_lbl,
        
        # Touch Settings
        'X1_BAND': x1_band,
        'X2_BAND': x2_band,
        'X2_COMPARE_WITH': x2_comp,
        'X2_SHOULD_BE': x2_should,
        'X2_MIN_DIST_PCT': x2_dist,
        'X3_MIN_DIST_BELOW_X2_PCT': x3_dist,
        
        'Y1_BAND': y1_band,
        'Y2_BAND': y2_band,
        'Y2_COMPARE_WITH': y2_comp,
        'Y2_SHOULD_BE': y2_should,
        'Y2_MIN_DIST_PCT': y2_dist,
        'Y3_MIN_DIST_ABOVE_Y2_PCT': y3_dist,
        
        'L1_BAND': l1_band,
        'L2_BAND': l2_band,
        'L2_COMPARE_WITH': l2_comp,
        'L2_SHOULD_BE': l2_should,
        'L2_MIN_DIST_PCT': l2_dist,
        'L3_MIN_DIST_BELOW_L2_PCT': l3_dist,
        
        'S1_BAND': s1_band,
        'S2_BAND': s2_band,
        'S2_COMPARE_WITH': s2_comp,
        'S2_SHOULD_BE': s2_should,
        'S2_MIN_DIST_PCT': s2_dist,
        'S3_MIN_DIST_ABOVE_S2_PCT': s3_dist,
        
        'M1_BAND': m1_band,
        'M2_BAND': m2_band,
        'M2_COMPARE_WITH': m2_comp,
        'M2_SHOULD_BE': m2_should,
        'M2_MIN_DIST_PCT': m2_dist,
        'M3_MIN_DIST_BELOW_M2_PCT': m3_dist,
        
        'N1_BAND': n1_band,
        'N2_BAND': n2_band,
        'N2_COMPARE_WITH': n2_comp,
        'N2_SHOULD_BE': n2_should,
        'N2_MIN_DIST_PCT': n2_dist,
        'N3_MIN_DIST_ABOVE_N2_PCT': n3_dist
    }

    run_live_trading(selected_trade_pairs_tv, timeframe, config_overrides)
    
    # Initialize (shared) data manager for fast, uncached live updates
    data_manager = st.session_state.get("_chart_data_manager")
    if data_manager is None:
        data_manager = DataManager()
        st.session_state["_chart_data_manager"] = data_manager
    
    # Data Fetching Logic (Optimized for Live Updates)
    df = pd.DataFrame()
    
    # Check if we have cached data for this symbol/timeframe
    if st.session_state.get("_data_cache_version") != DATA_CACHE_VERSION:
        st.session_state.data_cache = {}
        st.session_state.chart_engines = {}
        st.session_state["_data_cache_version"] = DATA_CACHE_VERSION

    if 'data_cache' not in st.session_state:
        st.session_state.data_cache = {}
        
    # If not cached or symbol changed, fetch full history
    if cache_key not in st.session_state.data_cache:
         try:
            df = fetch_candles(
                symbol,
                timeframe,
                limit=int(chart_fetch_limit),
                since_ms=effective_since_ms,
                until_ms=effective_until_ms,
            )
            st.session_state.data_cache[cache_key] = df
         except Exception as e:
            st.error(f"Error fetching initial data: {e}")
    else:
        # Use cached data
        df = st.session_state.data_cache[cache_key]

    # Live Updates: Prefer WebSocket, fallback to fast REST (uncached)
    if auto_refresh and not df.empty and chart_until_ms is None:
        updated = False
        last_ts = df["timestamp"].iloc[-1]

        ws_stream = st.session_state.get("_chart_ws_stream") if bool(use_ws_live) else None
        if ws_stream is not None:
            ws_new_rows = []
            while True:
                try:
                    item = ws_stream.queue.get_nowait()
                except queue.Empty:
                    break
                if not isinstance(item, dict) or not item.get("closed"):
                    continue
                try:
                    ts = pd.to_datetime(int(item.get("timestamp_ms")), unit="ms")
                except Exception:
                    continue
                if ts <= last_ts:
                    continue
                ws_new_rows.append(
                    {
                        "timestamp": ts,
                        "open": float(item.get("open")),
                        "high": float(item.get("high")),
                        "low": float(item.get("low")),
                        "close": float(item.get("close")),
                        "volume": float(item.get("volume", 0.0)),
                    }
                )

            if ws_new_rows:
                df = pd.concat([df, pd.DataFrame(ws_new_rows)], ignore_index=True)
                updated = True
        else:
            try:
                ohlcv = data_manager.exchange.fetch_ohlcv(symbol, timeframe, limit=50)
                if ohlcv and len(ohlcv) > 1:
                    # Drop the potentially-open candle; keep closed candles only.
                    ohlcv = ohlcv[:-1]
                if ohlcv:
                    latest_df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    latest_df = latest_df.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
                    latest_df["timestamp"] = pd.to_datetime(latest_df["timestamp"], unit="ms")
                    latest_df = latest_df[latest_df["timestamp"] > last_ts]
                    if not latest_df.empty:
                        df = pd.concat([df, latest_df], ignore_index=True)
                        updated = True
            except Exception as e:
                st.warning(f"Could not update live data: {e}")

        if updated:
            max_keep = int(chart_fetch_limit)
            if len(df) > max_keep:
                df = df.iloc[-max_keep:].reset_index(drop=True)
            st.session_state.data_cache[cache_key] = df

    replay_playing = bool(st.session_state.get("replay_playing", False))
    # Use user-configurable speed and step values from sidebar
    replay_speed = float(st.session_state.get("replay_speed_slider", REPLAY_SPEED))
    replay_step = int(st.session_state.get("replay_step_input", REPLAY_STEP))
    replay_marker_ts = None

    df_full = df
    if replay_enabled and not df_full.empty:
        replay_total = len(df_full)
        replay_index = st.session_state.get("replay_index")

        if replay_index is None:
            anchor = st.session_state.get("replay_anchor_ts")
            if anchor is None:
                replay_index = replay_total - 1
            else:
                anchor_utc = _from_gmt3(anchor)
                if anchor_utc is None:
                    replay_index = replay_total - 1
                else:
                    df_min = df_full["timestamp"].iloc[0]
                    df_max = df_full["timestamp"].iloc[-1]
                    if anchor_utc < df_min or anchor_utc > df_max:
                        st.sidebar.warning(
                            "Replay start is outside loaded data. Increase Chart Candle Limit "
                            "or set a Start/End Date that includes the target."
                        )
                    replay_index = int(df_full["timestamp"].searchsorted(anchor_utc, side="right") - 1)
            replay_index = max(0, min(replay_index, replay_total - 1))
            st.session_state["replay_index"] = replay_index

        replay_playing = bool(st.session_state.get("replay_playing", False))
        if replay_playing:
            next_index = replay_index + replay_step
            if next_index >= replay_total:
                replay_index = replay_total - 1
                st.session_state["replay_playing"] = False
                replay_playing = False
            else:
                replay_index = next_index
            st.session_state["replay_index"] = replay_index

        if replay_index is None:
            replay_index = replay_total - 1

        df = df_full.iloc[: replay_index + 1]

        replay_ts = _to_gmt3(df_full["timestamp"].iloc[replay_index]) if replay_index is not None else None
        if replay_ts is not None:
            replay_marker_ts = replay_ts
            st.sidebar.caption(
                f"Replay bar: {replay_index + 1}/{replay_total} @ {replay_ts.strftime('%Y-%m-%d %H:%M:%S')}"
            )

    
    if df.empty:
        st.error("No data fetched. Please check the symbol or API connection.")
    else:
        def _snapshot_state(s: YulaState, sig) -> dict:
            return {
                "x_range_active": getattr(s, "x_range_active", False),
                "x_range_high": getattr(s, "x_range_high", None),
                "x_range_low": getattr(s, "x_range_low", None),
                "y_range_active": getattr(s, "y_range_active", False),
                "y_range_high": getattr(s, "y_range_high", None),
                "y_range_low": getattr(s, "y_range_low", None),
                "l_range_high": getattr(s, "l_range_high", None),
                "l_range_low": getattr(s, "l_range_low", None),
                "s_range_high": getattr(s, "s_range_high", None),
                "s_range_low": getattr(s, "s_range_low", None),
                "m_range_active": getattr(s, "m_range_active", False),
                "m_range_high": getattr(s, "m_range_high", None),
                "m_range_low": getattr(s, "m_range_low", None),
                "n_range_active": getattr(s, "n_range_active", False),
                "n_range_high": getattr(s, "n_range_high", None),
                "n_range_low": getattr(s, "n_range_low", None),
                "x_fibs": dict(getattr(s, "x_fibs", {}) or {}) if isinstance(getattr(s, "x_fibs", {}), dict) else {},
                "y_fibs": dict(getattr(s, "y_fibs", {}) or {}) if isinstance(getattr(s, "y_fibs", {}), dict) else {},
                "l_fibs": dict(getattr(s, "l_fibs", {}) or {}) if isinstance(getattr(s, "l_fibs", {}), dict) else {},
                "s_fibs": dict(getattr(s, "s_fibs", {}) or {}) if isinstance(getattr(s, "s_fibs", {}), dict) else {},
                "m_fibs": dict(getattr(s, "m_fibs", {}) or {}) if isinstance(getattr(s, "m_fibs", {}), dict) else {},
                "n_fibs": dict(getattr(s, "n_fibs", {}) or {}) if isinstance(getattr(s, "n_fibs", {}), dict) else {},
                "signal": sig,
            }

        config_sig = _config_signature(config_overrides)
        engine_key = f"{cache_key}::{config_sig}"
        if replay_enabled:
            engine_key = f"{engine_key}::replay"
        chart_engines = st.session_state.setdefault("chart_engines", {})

        def _build_engine():
            strat = YulaStrategy(config_overrides=config_overrides)
            stt = YulaState()
            hist = []
            for idx, row in enumerate(df.itertuples(index=False), start=0):
                candle = {
                    "timestamp": row.timestamp,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                }
                sig, stt = strat.calculate(candle, stt, idx)
                hist.append(_snapshot_state(stt, sig))
            return {
                "df": df,
                "strategy": strat,
                "state": stt,
                "state_history": hist,
                "last_ts": df["timestamp"].iloc[-1] if not df.empty else None,
                "next_index": len(df),
            }

        engine = chart_engines.get(engine_key)
        if engine is None:
            engine = _build_engine()
            chart_engines[engine_key] = engine
        else:
            # Keep the engine aligned with the displayed df window
            engine["df"] = df
            if len(engine.get("state_history", [])) > len(df):
                engine["state_history"] = engine["state_history"][-len(df):]

            last_processed_ts = engine.get("last_ts")
            last_df_ts = df["timestamp"].iloc[-1] if not df.empty else None
            if last_processed_ts is None or (
                replay_enabled and last_df_ts is not None and last_processed_ts > last_df_ts
            ):
                engine = _build_engine()
                chart_engines[engine_key] = engine
            else:
                start_idx = int(df["timestamp"].searchsorted(last_processed_ts, side="right"))
                new_df = df.iloc[start_idx:]
                if not new_df.empty:
                    strat = engine["strategy"]
                    stt = engine["state"]
                    hist = engine["state_history"]
                    next_index = int(engine.get("next_index", len(hist)))
                    for row in new_df.itertuples(index=False):
                        candle = {
                            "timestamp": row.timestamp,
                            "open": row.open,
                            "high": row.high,
                            "low": row.low,
                            "close": row.close,
                            "volume": row.volume,
                        }
                        sig, stt = strat.calculate(candle, stt, next_index)
                        hist.append(_snapshot_state(stt, sig))
                        next_index += 1
                        last_processed_ts = row.timestamp

                    engine["state"] = stt
                    engine["state_history"] = hist
                    engine["last_ts"] = last_processed_ts
                    engine["next_index"] = next_index

        state = engine["state"]
        state_history = engine["state_history"]
        
        # --- 6. Visualizer ---
        trades = getattr(state, 'trades', [])
        
        visualizer = Visualizer()
        df_plot = df
        state_history_view = state_history
        if len(state_history) != len(df_plot):
            state_history_view = state_history[-len(df_plot):]
        fig = visualizer.plot_strategy(
            df_plot,
            state_history_view,
            trades=trades,
            config=config_overrides,
            max_display_candles=int(render_candle_limit),
        )
        goto_token = st.session_state.get("chart_goto_token", "base")
        fig.update_layout(uirevision=f"{symbol}:{timeframe}:{goto_token}")

        goto_cfg = st.session_state.get("chart_goto")
        if goto_cfg:
            df_min = _to_gmt3(df_plot["timestamp"].min()) if not df_plot.empty else None
            df_max = _to_gmt3(df_plot["timestamp"].max()) if not df_plot.empty else None

            def _as_local_naive(value):
                if value is None:
                    return None
                ts = pd.to_datetime(value)
                if isinstance(ts, pd.Timestamp) and ts.tzinfo is not None:
                    ts = ts.tz_convert("UTC").tz_localize(None)
                return ts

            start = None
            end = None
            if goto_cfg.get("mode") == "date":
                target = _as_local_naive(goto_cfg.get("target"))
                window = int(goto_cfg.get("window") or 200)
                tf_seconds = {
                    "1m": 60,
                    "3m": 180,
                    "5m": 300,
                    "15m": 900,
                    "30m": 1800,
                    "1h": 3600,
                    "2h": 7200,
                    "4h": 14400,
                    "1d": 86400,
                }.get(timeframe, 0)
                if target is not None and tf_seconds:
                    half = dt.timedelta(seconds=(tf_seconds * window) / 2)
                    start = target - half
                    end = target + half
            elif goto_cfg.get("mode") == "range":
                start = _as_local_naive(goto_cfg.get("start"))
                end = _as_local_naive(goto_cfg.get("end"))

            if start is not None and end is not None and start > end:
                start, end = end, start

            if start is not None and end is not None and df_min is not None and df_max is not None:
                if (df_max - df_min) <= (end - start):
                    start = df_min
                    end = df_max
                else:
                    if start < df_min:
                        shift = df_min - start
                        start += shift
                        end += shift
                    if end > df_max:
                        shift = end - df_max
                        start -= shift
                        end -= shift
                    if start < df_min:
                        start = df_min
                    if end > df_max:
                        end = df_max

            if start is not None and end is not None:
                fig.update_xaxes(range=[start, end])

        if replay_marker_ts is not None:
            fig.add_vline(x=replay_marker_ts, line_width=2, line_color="#2E77FF")

        realtime_enabled = bool(realtime_candle) and chart_until_ms is None and not replay_enabled
        if realtime_enabled and not df_plot.empty:
            try:
                tf_seconds = int(data_manager.exchange.parse_timeframe(timeframe))
            except Exception:
                tf_seconds = {
                    "1m": 60,
                    "3m": 180,
                    "5m": 300,
                    "15m": 900,
                    "30m": 1800,
                    "1h": 3600,
                    "2h": 7200,
                    "4h": 14400,
                    "1d": 86400,
                }.get(timeframe, 0)

            if tf_seconds:
                last_close = float(df_plot["close"].iloc[-1])
                last_ts = pd.to_datetime(df_plot["timestamp"].iloc[-1])
                if isinstance(last_ts, pd.Timestamp) and last_ts.tzinfo is not None:
                    last_ts = last_ts.tz_convert("UTC").tz_localize(None)
                live_open_ts = last_ts + pd.Timedelta(seconds=tf_seconds)
                live_x = live_open_ts + pd.Timedelta(hours=3)

                live_trace = go.Candlestick(
                    x=[live_x],
                    open=[last_close],
                    high=[last_close],
                    low=[last_close],
                    close=[last_close],
                    name="LIVE",
                    showlegend=False,
                    increasing=dict(line=dict(color="#089981"), fillcolor="#089981"),
                    decreasing=dict(line=dict(color="#F23645"), fillcolor="#F23645"),
                    hoverinfo="skip",
                )

                fig.add_trace(live_trace)

        plot_config = {
            "scrollZoom": True,
            "displayModeBar": True,
            "displaylogo": False,
            "responsive": True,
        }
        if replay_enabled:
            # Check if selection mode is active (user clicked "Bölge Seç")
            replay_selecting = st.session_state.get("replay_selecting", False)
            
            # Only add selection trace when in selection mode (no blue shadow in normal mode)
            if replay_selecting and not df_plot.empty:
                pick_ts = pd.to_datetime(df_plot["timestamp"])
                if getattr(pick_ts.dt, "tz", None) is not None:
                    pick_ts = pick_ts.dt.tz_convert("UTC").dt.tz_localize(None)
                pick_ts = pick_ts + pd.Timedelta(hours=3)
                pick_ts = pick_ts.reset_index(drop=True)
                pick_idx = pd.Series(range(len(pick_ts)))
                
                # Use only close values for better performance
                fig.add_trace(
                    go.Scatter(
                        x=pick_ts,
                        y=df_plot["close"].reset_index(drop=True),
                        mode="markers",
                        marker=dict(size=15, color="rgba(0,0,0,0)"),  # Completely transparent
                        hoverinfo="none",
                        showlegend=False,
                        customdata=pick_idx,
                        name="__replay_pick__",
                    )
                )
                
                # Enable crosshair (blue vertical line) in selection mode
                fig.update_layout(
                    clickmode="event+select",
                    hovermode="x",
                    hoverdistance=1000,
                    spikedistance=1000,
                )
                fig.update_xaxes(
                    showspikes=True,
                    spikemode="across",
                    spikesnap="cursor",
                    spikethickness=2,
                    spikedash="solid",
                    spikecolor="#2E77FF",
                )
            else:
                # Normal mode - no crosshair, no selection trace
                fig.update_layout(
                    clickmode="none",
                    hovermode="x unified",
                )
                fig.update_xaxes(showspikes=False)
            
            fig.update_yaxes(showspikes=False)
            
            # Render chart
            selection = st.plotly_chart(
                fig,
                use_container_width=True,
                config=plot_config,
                on_select="rerun" if replay_selecting else "ignore",
                selection_mode="points",
                key="replay_chart",
            )
            
            # Only process selection when in selection mode and not playing
            if replay_playing or not replay_selecting:
                selection = None
            selection_state = selection if selection is not None else st.session_state.get("replay_chart")
            selection_data = None
            if isinstance(selection_state, dict):
                selection_data = selection_state.get("selection", selection_state)
            elif hasattr(selection_state, "selection"):
                selection_data = selection_state.selection
            points = None
            point_indices = None
            if isinstance(selection_data, dict):
                points = selection_data.get("points")
                point_indices = selection_data.get("point_indices")
            elif hasattr(selection_data, "points"):
                points = selection_data.points
                point_indices = getattr(selection_data, "point_indices", None)
            selected_ts = None
            if points:
                for point in points:
                    if isinstance(point, dict) and point.get("x") is not None:
                        selected_ts = pd.to_datetime(point.get("x"))
                        break
                if selected_ts is None:
                    point_index = None
                    for point in points:
                        if not isinstance(point, dict):
                            continue
                        if point.get("customdata") is not None:
                            point_index = int(point.get("customdata"))
                            break
                        point_index = point.get("point_index", point.get("pointIndex"))
                        if point_index is not None:
                            break
                    if point_index is not None and not df_plot.empty:
                        idx = int(point_index)
                        base_idx = idx % len(df_plot)
                        if 0 <= base_idx < len(df_plot):
                            selected_ts = _to_gmt3(df_plot["timestamp"].iloc[base_idx])
            if selected_ts is None and point_indices and not df_plot.empty:
                idx = int(point_indices[0])
                base_idx = idx % len(df_plot)
                if 0 <= base_idx < len(df_plot):
                    selected_ts = _to_gmt3(df_plot["timestamp"].iloc[base_idx])
            if isinstance(selected_ts, pd.Timestamp) and selected_ts.tzinfo is not None:
                selected_ts = selected_ts.tz_convert("UTC").tz_localize(None)
            if selected_ts is not None:
                selected_ts = pd.to_datetime(selected_ts).to_pydatetime().replace(microsecond=0)
                last_pick = st.session_state.get("_replay_pick_last")
                if last_pick != selected_ts:
                    st.session_state["_replay_pick_last"] = selected_ts
                    st.session_state["replay_anchor_ts"] = selected_ts
                    anchor_utc = _from_gmt3(selected_ts)
                    if anchor_utc is not None and not df_full.empty:
                        idx = int(df_full["timestamp"].searchsorted(anchor_utc, side="right") - 1)
                        idx = max(0, min(idx, len(df_full) - 1))
                        st.session_state["replay_index"] = idx
                        st.session_state["replay_playing"] = False
                    # Auto-disable selection mode after successful selection
                    st.session_state["replay_selecting"] = False
                    st.rerun()
        else:
            render_plotly_chart(
                fig,
                tv_axis_scaling=bool(tv_axis_scaling),
                realtime_candle=realtime_enabled,
                symbol=symbol,
                timeframe=timeframe,
                max_points=int(render_candle_limit),
                auto_scroll=bool(auto_scroll_live) and not replay_enabled,
            )
        
        # --- 7. Trade History Table ---
        if trades:
            st.subheader("İşlem Geçmişi (Trade History)")
            trade_df = pd.DataFrame(trades)
            if 'time' in trade_df.columns:
                trade_df['time'] = trade_df['time'].apply(_to_gmt3)
            
            cols = ['time', 'type', 'price', 'size', 'comment']
            cols = [c for c in cols if c in trade_df.columns]
            trade_df = trade_df[cols]
            
            st.dataframe(trade_df, use_container_width=True)
        else:
            st.info("Henüz işlem geçmişi yok.")

        # --- 8. Backtest (TradingView-style) ---
        st.subheader("Backtest")
        if df.empty:
            st.info("No data available for backtest.")
        else:
            backtest_start_ts = pd.to_datetime(int(bt_since_ms), unit="ms") if bt_since_ms is not None else None
            backtest_end_ts = pd.to_datetime(int(bt_until_ms), unit="ms") if bt_until_ms is not None else None

            df_bt = df
            if backtest_end_ts is not None:
                df_bt = df[df["timestamp"] <= backtest_end_ts]

            last_close = None
            last_close_time = None
            if not df_bt.empty:
                last_close = float(df_bt["close"].iloc[-1])
                last_close_time = _normalize_time(df_bt["timestamp"].iloc[-1])

            effective_end_ts = backtest_end_ts if backtest_end_ts is not None else last_close_time

            if bt_size_mode == "percent":
                percent_equity = float(bt_percent_equity or 0.0)
                fixed_notional = float(getattr(cfg_backtest, "ORDER_NOTIONAL_USDT", 0.0))
                size_desc = f"{percent_equity:.1f}% of equity"
            else:
                fixed_notional = float(bt_fixed_notional or 0.0)
                percent_equity = float(bt_percent_equity or 0.0) if bt_percent_equity is not None else 0.0
                size_desc = f"{fixed_notional:.2f} USDT notional"

            summary, bt_trades_df, exec_df, open_info = _build_backtest(
                trades,
                candle_df=df_bt,
                start_ts=backtest_start_ts,
                end_ts=effective_end_ts,
                initial_balance=float(bt_initial_balance),
                size_mode=bt_size_mode,
                fixed_notional=fixed_notional,
                percent_equity=percent_equity,
                leverage=float(bt_leverage),
                fee_rate=float(bt_fee_rate),
                last_close=last_close,
                close_time=effective_end_ts,
                close_open_at_end=bool(backtest_close_end),
                # Kar Çekimi Parametreleri
                enable_profit_withdrawal=bt_enable_profit_withdrawal,
                growth_threshold_pct=float(bt_growth_threshold),
                withdrawal_rate_pct=float(bt_withdrawal_rate),
                use_reserve_on_max_loss=bt_use_reserve_on_max_loss,
                min_capital_requirement=float(bt_min_withdr_capital),
            )

            def _fmt_range(ts):
                if ts is None:
                    return "All"
                ts_local = _to_gmt3(ts)
                if ts_local is None:
                    return "All"
                return ts_local.strftime("%Y-%m-%d %H:%M")

            st.caption(
                f"Range: {_fmt_range(backtest_start_ts)} -> {_fmt_range(effective_end_ts)} (UTC+3). "
                f"Initial: {float(bt_initial_balance):.2f} USDT, Size: {size_desc}, "
                f"Leverage: {float(bt_leverage):.2f}x, Fee: {float(bt_fee_rate):.4f}%/side."
            )

            pf_val = summary.get("profit_factor", 0.0)
            pf_text = "inf" if pf_val == float("inf") else f"{pf_val:.2f}"

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Initial Balance", f"{summary.get('initial_balance', 0.0):.2f}")
            col2.metric("Ending Balance", f"{summary.get('ending_balance', 0.0):.2f}")
            col3.metric("Net PnL (USDT)", f"{summary.get('net_profit_usdt', 0.0):.2f}")
            col4.metric("Net PnL (%)", f"{summary.get('net_profit_pct', 0.0):.2f}%")

            col5, col6, col7, col8 = st.columns(4)
            col5.metric("Win Rate", f"{summary.get('win_rate', 0.0):.2f}%")
            col6.metric("Profit Factor", pf_text)
            col7.metric("Max Drawdown (USDT)", f"{summary.get('max_drawdown_usdt', 0.0):.2f}")
            col8.metric("Max Drawdown (%)", f"{summary.get('max_drawdown_pct', 0.0):.2f}%")

            col9, col10, col11, col12 = st.columns(4)
            col9.metric("Total Trades", f"{summary.get('total_trades', 0)}")
            col10.metric("Avg Trade (USDT)", f"{summary.get('avg_trade_usdt', 0.0):.2f}")
            col11.metric(
                "Avg Win / Avg Loss",
                f"{summary.get('avg_win_usdt', 0.0):.2f} / {summary.get('avg_loss_usdt', 0.0):.2f}",
            )
            col12.metric("Fees (USDT)", f"{summary.get('fees_usdt', 0.0):.2f}")

            # --- KAR ÇEKİMİ BİLGİLERİ ---
            if bt_enable_profit_withdrawal:
                st.markdown("---")
                st.caption("💰 **Kar Çekimi Bilgileri**")
                wcol1, wcol2, wcol3, wcol4 = st.columns(4)
                wcol1.metric("Toplam Çekilen", f"${summary.get('total_withdrawals_usdt', 0.0):.2f}")
                wcol2.metric("Çekim Sayısı", f"{summary.get('withdrawal_count', 0)}")
                wcol3.metric("Kalan Yedek", f"${summary.get('final_reserve_usdt', 0.0):.2f}")
                wcol4.metric("Reserve Enjeksiyonu", f"{summary.get('reserve_injection_count', 0)}")

            # --- RİSK YÖNETİMİ BİLGİLERİ ---
            st.markdown("---")
            st.caption("🛡️ **Risk Yönetimi**")
            rcol1, rcol2 = st.columns(2)
            rcol1.metric("Max Loss Ayarı", f"%{float(max_loss_pct):.1f}")
            
            ml_hits = 0
            if exec_df is not None and not exec_df.empty and "Comment" in exec_df.columns:
                 ml_hits = len(exec_df[exec_df["Comment"].astype(str).str.contains("Max Loss", na=False)])
            
            rcol2.metric("Max Loss Tetiklenme", f"{ml_hits}")

            if open_info:
                st.warning(
                    "Open position remains at the end of the range. "
                    "Enable 'Close Open Position At End' to include it in results."
                )


            if bt_trades_df is not None and not bt_trades_df.empty:
                # TradingView tarzı tablo görünümü
                st.subheader("📊 İşlem Listesi (Trade List)")
                
                # Kolonları formatla
                display_df = bt_trades_df.copy()
                if "Fiyat" in display_df.columns:
                    display_df["Fiyat"] = display_df["Fiyat"].apply(lambda x: f"{x:.4f}" if pd.notnull(x) else "")
                if "Net PnL" in display_df.columns:
                    display_df["Net PnL"] = display_df["Net PnL"].apply(lambda x: f"{x:+.2f} USD" if pd.notnull(x) else "")
                if "Kümülatif PnL" in display_df.columns:
                    display_df["Kümülatif PnL"] = display_df["Kümülatif PnL"].apply(lambda x: f"{x:+.2f} USD" if pd.notnull(x) else "")
                if "Kâr/Zarar %" in display_df.columns:
                    display_df["Kâr/Zarar %"] = display_df["Kâr/Zarar %"].apply(lambda x: f"{x:+.2f}%" if pd.notnull(x) else "")
                if "Yükselmiş (USD)" in display_df.columns:
                    display_df["Yükselmiş (USD)"] = display_df["Yükselmiş (USD)"].apply(lambda x: f"+{x:.2f} USD" if x > 0 else "")
                if "Yükselmiş (%)" in display_df.columns:
                    display_df["Yükselmiş (%)"] = display_df["Yükselmiş (%)"].apply(lambda x: f"+{x:.2f}%" if x > 0 else "")
                if "Düşüş (USD)" in display_df.columns:
                    display_df["Düşüş (USD)"] = display_df["Düşüş (USD)"].apply(lambda x: f"-{x:.2f} USD" if x > 0 else "")
                if "Düşüş (%)" in display_df.columns:
                    display_df["Düşüş (%)"] = display_df["Düşüş (%)"].apply(lambda x: f"-{x:.2f}%" if x > 0 else "")
                if "Pozisyon Büyüklüğü" in display_df.columns:
                    display_df["Pozisyon Büyüklüğü"] = display_df["Pozisyon Büyüklüğü"].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "")
                if "Bakiye" in display_df.columns:
                    display_df["Bakiye"] = display_df["Bakiye"].apply(lambda x: f"${x:.2f}" if pd.notnull(x) else "")
                
                st.dataframe(display_df, use_container_width=True, height=400)
            else:
                st.info("No closed trades in backtest range.")


            if bool(backtest_show_exec) and exec_df is not None and not exec_df.empty:
                st.subheader("Backtest Executions")
                st.dataframe(exec_df, use_container_width=True)

            summary_export = dict(summary)
            summary_export["symbol"] = symbol
            summary_export["timeframe"] = timeframe
            summary_export["range_start"] = _fmt_range(backtest_start_ts)
            summary_export["range_end"] = _fmt_range(effective_end_ts)
            summary_export["size_mode"] = bt_size_mode
            summary_export["percent_equity"] = percent_equity
            summary_export["fixed_notional"] = fixed_notional
            summary_export["leverage"] = float(bt_leverage)
            summary_export["fee_rate_pct"] = float(bt_fee_rate)
            summary_export["open_trade"] = json.dumps(open_info, default=str) if open_info else ""

            xls_bytes = _build_backtest_excel(summary_export, bt_trades_df, exec_df)
            st.download_button(
                "Download Backtest XLSX",
                data=xls_bytes,
                file_name=f"backtest_{symbol.replace('/', '_')}_{timeframe}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        # Metrics
        st.subheader("Strategy Metrics")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("X Range Active", "Yes" if state.x_range_active else "No")
        col2.metric("Y Range Active", "Yes" if state.y_range_active else "No")
        col3.metric("L Range (Bull Mom)", "Yes" if state.l_range_high else "No")
        col4.metric("S Range (Bear Mom)", "Yes" if state.s_range_high else "No")

    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()
    if replay_enabled and replay_playing:
        delay = 1.0 / max(replay_speed, 0.1)
        time.sleep(delay)
        st.rerun()
