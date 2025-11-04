#!/usr/bin/env python3
"""
Market Data Feed
Real-time price streaming with 200-candle history buffers and basic indicators
"""

import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import deque
import numpy as np
from dataclasses import dataclass

from .broker_api import OandaBroker, BrokerPrice

logger = logging.getLogger(__name__)


@dataclass
class PriceBar:
    """OHLCV price bar"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class MarketDataFeed:
    """Real-time market data feed with price history"""
    
    def __init__(self, broker: OandaBroker, instruments: List[str], update_interval: int = 5):
        """Initialize market data feed"""
        self.broker = broker
        self.instruments = instruments
        self.update_interval = update_interval
        
        # Price storage: instrument -> deque of PriceBar (ring buffer, max 200)
        self.price_history: Dict[str, deque] = {inst: deque(maxlen=200) for inst in instruments}
        
        # Current prices: instrument -> BrokerPrice
        self.current_prices: Dict[str, BrokerPrice] = {}
        
        # Threading
        self.running = False
        self.data_thread: Optional[threading.Thread] = None
        
        # Data freshness tracking
        self.last_update: Dict[str, datetime] = {}
        
        logger.info(f"✅ Market data feed initialized for {len(instruments)} instruments")
    
    def start(self):
        """Start the data feed"""
        if self.running:
            logger.warning("Data feed already running")
            return
        
        self.running = True
        self.data_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.data_thread.start()
        logger.info("✅ Market data feed started")
    
    def stop(self):
        """Stop the data feed"""
        self.running = False
        if self.data_thread:
            self.data_thread.join(timeout=10)
        logger.info("✅ Market data feed stopped")
    
    def _update_loop(self):
        """Main update loop"""
        logger.info("🔄 Starting market data update loop")
        
        while self.running:
            try:
                # Get current prices from broker
                prices = self.broker.get_prices(self.instruments)
                
                for instrument, price in prices.items():
                    self.current_prices[instrument] = price
                    self.last_update[instrument] = datetime.utcnow()
                    
                    # Create price bar from current bid/ask (using mid price)
                    mid_price = (price.bid + price.ask) / 2
                    
                    # If we have previous bar, update high/low, otherwise create new bar
                    if instrument in self.price_history and len(self.price_history[instrument]) > 0:
                        last_bar = self.price_history[instrument][-1]
                        
                        # If same minute, update current bar
                        if (price.timestamp - last_bar.timestamp).total_seconds() < 60:
                            last_bar.high = max(last_bar.high, mid_price)
                            last_bar.low = min(last_bar.low, mid_price)
                            last_bar.close = mid_price
                        else:
                            # New minute, create new bar
                            new_bar = PriceBar(
                                timestamp=price.timestamp,
                                open=mid_price,
                                high=mid_price,
                                low=mid_price,
                                close=mid_price
                            )
                            self.price_history[instrument].append(new_bar)
                    else:
                        # First bar
                        new_bar = PriceBar(
                            timestamp=price.timestamp,
                            open=mid_price,
                            high=mid_price,
                            low=mid_price,
                            close=mid_price
                        )
                        self.price_history[instrument].append(new_bar)
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"❌ Error updating market data: {e}", exc_info=True)
                time.sleep(10)  # Wait longer on error
    
    def get_current_price(self, instrument: str) -> Optional[BrokerPrice]:
        """Get current price for an instrument"""
        return self.current_prices.get(instrument)
    
    def get_price_history(self, instrument: str, num_bars: int = None) -> List[PriceBar]:
        """Get price history for an instrument"""
        if instrument not in self.price_history:
            return []
        
        history = list(self.price_history[instrument])
        if num_bars:
            return history[-num_bars:]
        return history
    
    def get_close_prices(self, instrument: str, num_bars: int = None) -> List[float]:
        """Get close prices as a list"""
        history = self.get_price_history(instrument, num_bars)
        return [bar.close for bar in history]
    
    def calculate_sma(self, instrument: str, period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        closes = self.get_close_prices(instrument, period)
        if len(closes) < period:
            return None
        return np.mean(closes[-period:])
    
    def calculate_ema(self, instrument: str, period: int, alpha: float = None) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        closes = self.get_close_prices(instrument, period * 2)  # Need more data for EMA
        if len(closes) < period:
            return None
        
        if alpha is None:
            alpha = 2.0 / (period + 1)
        
        # Calculate EMA
        ema = closes[0]
        for price in closes[1:]:
            ema = alpha * price + (1 - alpha) * ema
        
        return ema
    
    def calculate_atr(self, instrument: str, period: int = 14) -> Optional[float]:
        """Calculate Average True Range"""
        history = self.get_price_history(instrument, period + 1)
        if len(history) < period + 1:
            return None
        
        true_ranges = []
        for i in range(1, len(history)):
            high_low = history[i].high - history[i].low
            high_close = abs(history[i].high - history[i-1].close)
            low_close = abs(history[i].low - history[i-1].close)
            tr = max(high_low, high_close, low_close)
            true_ranges.append(tr)
        
        if not true_ranges:
            return None
        
        return np.mean(true_ranges[-period:])
    
    def is_data_fresh(self, instrument: str, max_age_seconds: int = 60) -> bool:
        """Check if data is fresh (updated within max_age_seconds)"""
        if instrument not in self.last_update:
            return False
        
        age = (datetime.utcnow() - self.last_update[instrument]).total_seconds()
        return age <= max_age_seconds
    
    def get_all_current_prices(self) -> Dict[str, BrokerPrice]:
        """Get all current prices"""
        return self.current_prices.copy()
    
    def add_instruments(self, instruments: List[str]):
        """Add instruments to monitor"""
        for inst in instruments:
            if inst not in self.price_history:
                self.price_history[inst] = deque(maxlen=200)
                logger.info(f"✅ Added instrument: {inst}")
        
        self.instruments.extend([inst for inst in instruments if inst not in self.instruments])
        self.instruments = list(set(self.instruments))  # Remove duplicates
