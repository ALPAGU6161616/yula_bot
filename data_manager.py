import ccxt
import pandas as pd
import time
from config import Config

class DataManager:
    def __init__(self):
        config = {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
            }
        }
        
        if Config.API_KEY != "YOUR_API_KEY" and Config.API_SECRET != "YOUR_API_SECRET":
            config['apiKey'] = Config.API_KEY
            config['secret'] = Config.API_SECRET
            
        # Use the USD-M futures client explicitly so symbol resolution stays on
        # fapi endpoints and does not fall back to COIN-M (dapi) market loading.
        self.exchange = ccxt.binanceusdm(config)
        try:
            if hasattr(self.exchange, "load_time_difference"):
                self.exchange.load_time_difference()
        except Exception:
            pass
        if getattr(Config, "USE_TESTNET", False):
            try:
                self.exchange.set_sandbox_mode(True)
            except Exception:
                pass
        
    def fetch_initial_data(self, symbol, timeframe, limit=Config.HISTORICAL_CANDLE_LIMIT):
        """
        Fetches historical OHLCV data with pagination support for large limits.
        """
        print(f"Fetching initial data for {symbol} {timeframe} (Limit: {limit})...")
        all_candles = []
        
        # Binance max limit per request is usually 1000 or 1500
        batch_size = 1000
        
        # Calculate start time based on timeframe to optimize fetching if needed, 
        # but for simplicity/robustness we can fetch backwards or use since if we knew start.
        # However, ccxt/Binance mostly fetches 'most recent' if 'since' is missing.
        # To fetch 10,000 candles ending NOW, it's trickier with standard ccxt calls without 'since'.
        # But we can calculate a rough 'since' or just fetch repeatedly.
        
        # Method: Fetch most recent batch, then keep fetching older batches?
        # Binance API fetch_ohlcv without 'since' returns the LATEST candles.
        # To get older ones, we need to specify 'endTime' or work backwards.
        # CCXT generic fetch_ohlcv usually takes 'since'.
        
        # Let's try a simple approach: Calculate 'since' for 10,000 candles ago.
        try:
            duration_seconds = self.exchange.parse_timeframe(timeframe)
            duration_ms = duration_seconds * 1000
            now = self.exchange.milliseconds()
            since = now - (limit * duration_ms)
            
            while len(all_candles) < limit:
                # Adjust batch size for the last chunk
                remaining = limit - len(all_candles)
                current_limit = min(batch_size, remaining)
                
                # We use 'since' to fetch forward from that point
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=batch_size)
                
                if not ohlcv:
                    break
                
                all_candles.extend(ohlcv)
                
                # Update 'since' for next batch: time of last candle + 1 timeframe (or just +1ms)
                last_time = ohlcv[-1][0]
                since = last_time + 1
                
                # Safety break if we caught up to now
                if last_time >= now - duration_ms:
                    break
                    
                time.sleep(0.1) # Rate limit protection

            # If we got more than needed (due to batching), trim
            if len(all_candles) > limit:
                all_candles = all_candles[-limit:]

            df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Remove duplicates just in case
            df = df.drop_duplicates(subset=['timestamp'])
            
            return df
        except Exception as e:
            print(f"Error fetching initial data: {e}")
            return pd.DataFrame()

    def fetch_latest_candle(self, symbol, timeframe):
        """
        Fetches the most recent *closed* candle.
        """
        try:
            # Fetch 2 candles to ensure we get the last closed one
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=2)
            if not ohlcv:
                return None
            
            latest = ohlcv[-2]
            return {
                'timestamp': pd.to_datetime(latest[0], unit='ms'),
                'open': latest[1],
                'high': latest[2],
                'low': latest[3],
                'close': latest[4],
                'volume': latest[5]
            }
        except Exception as e:
            print(f"Error fetching latest candle: {e}")
            return None

    def get_server_time(self):
        return self.exchange.fetch_time()
