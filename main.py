import time
import pandas as pd
import copy
import sys
from config import Config
from data_manager import DataManager
from yula_strategy import YulaStrategy, YulaState
from trader import Trader
from visualizer import Visualizer

def main():
    print("Welcome to YULA Bot")
    print("1. Run Bot (Live Trading/Monitoring)")
    print("2. Visualize Strategy (Backtest/Chart)")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "2":
        run_visualization()
    else:
        run_bot()

def run_visualization():
    print("Starting Visualization Mode...")
    
    # Initialize
    data_manager = DataManager()
    strategy = YulaStrategy()
    state = YulaState()
    
    # Fetch Data
    print(f"Fetching data for {Config.SYMBOL}...")
    df = data_manager.fetch_initial_data(Config.SYMBOL, Config.TIMEFRAME)
    
    if df.empty:
        print("No data fetched. Exiting.")
        return

    print(f"Running strategy on {len(df)} candles...")
    state_history = []
    
    for index, row in df.iterrows():
        candle = {
            'timestamp': row['timestamp'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume']
        }
        
        # Calculate Strategy
        signal, state = strategy.calculate(candle, state, index)
        
        # Store state copy for visualization
        state_history.append(copy.deepcopy(state))
        
    print("Calculation complete. Generating chart...")
    visualizer = Visualizer()
    visualizer.plot_strategy(df, state_history)

def run_bot():
    print("Starting Yula Bot (Live Mode)...")
    
    # 1. Initialize Components
    data_manager = DataManager()
    strategy = YulaStrategy()
    state = YulaState()
    trader = Trader(data_manager.exchange)
    
    # 2. Warmup with Historical Data
    print("Warming up strategy...")
    df = data_manager.fetch_initial_data(Config.SYMBOL, Config.TIMEFRAME)
    
    if df.empty:
        print("No data fetched. Exiting.")
        return

    # Ensure warmup uses the last closed candle to avoid acting on an in-progress bar.
    latest_closed = data_manager.fetch_latest_candle(Config.SYMBOL, Config.TIMEFRAME)
    if latest_closed is not None and "timestamp" in latest_closed:
        df = df[df["timestamp"] <= latest_closed["timestamp"]].reset_index(drop=True)

    # Iterate through history to build state
    for index, row in df.iterrows():
        candle = {
            'timestamp': row['timestamp'],
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume']
        }
        
        # Calculate Strategy
        signal, state = strategy.calculate(candle, state, index)
        
    print("Warmup complete.")
    print(f"Current State: X-Range Active: {state.x_range_active}, Y-Range Active: {state.y_range_active}")

    # Start live trading from a clean execution state (ranges/momentum stay warmed up).
    state.trades = []
    state.position_size = 0
    state.pendingLongEntry = False
    state.pendingShortEntry = False
    state.pendingEntryBar = None
    state.pendingEntryReason = ""
    strategy._reset_position_state(state)
    trader.reset()
    
    # 3. Main Loop
    print("Entering main loop...")
    last_processed_ts = df["timestamp"].iloc[-1] if not df.empty else None
    next_index = len(df)
    while True:
        try:
            # Fetch latest candle
            latest_candle = data_manager.fetch_latest_candle(Config.SYMBOL, Config.TIMEFRAME)
            
            if latest_candle:
                if last_processed_ts is not None and latest_candle["timestamp"] <= last_processed_ts:
                    time.sleep(5)
                    continue

                last_processed_ts = latest_candle["timestamp"]

                # Calculate
                signal, state = strategy.calculate(latest_candle, state, next_index)
                next_index += 1

                # Execute based on strategy trade events
                trader.process_new_trades(state, latest_candle, Config.SYMBOL)

                print(f"Processed candle at {latest_candle['timestamp']}. Signal: {signal}")
                
            # Sleep
            time.sleep(5)  # Poll frequently; only acts on new closed candles
            
        except KeyboardInterrupt:
            print("Stopping bot...")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
