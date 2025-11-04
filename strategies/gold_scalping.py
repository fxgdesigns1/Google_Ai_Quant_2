#!/usr/bin/env python3
"""
Gold Scalping Strategy
Fast entries on Gold pullbacks with tight stops
"""

import logging
from typing import List, Dict
from datetime import datetime

from .base_strategy import BaseStrategy
from core.order_executor import TradeSignal
from core.market_data import MarketDataFeed

logger = logging.getLogger(__name__)


class GoldScalpingStrategy(BaseStrategy):
    """Scalping strategy for Gold with quick entries and exits"""
    
    def __init__(self, config: Dict):
        """Initialize gold scalping strategy"""
        super().__init__(config)
        
        # Strategy parameters
        self.pullback_depth_pct = config.get('pullback_depth_pct', 0.003)  # 0.3% pullback
        self.lookback_period = config.get('lookback_period', 20)  # 20 bars lookback
        self.min_confidence = config.get('min_confidence', 0.4)  # 40% minimum confidence
        self.trend_period = config.get('trend_period', 50)  # 50 bars for trend
        
        logger.info(f"✅ Gold Scalping Strategy initialized")
        logger.info(f"   Pullback depth: {self.pullback_depth_pct*100:.2f}%")
        logger.info(f"   Lookback period: {self.lookback_period} bars")
    
    def analyze(self, market_data: Dict) -> List[TradeSignal]:
        """Analyze market data and generate trade signals"""
        signals = []
        
        if not self.enabled:
            return signals
        
        # This strategy only trades XAU_USD
        if 'XAU_USD' not in self.instruments:
            return signals
        
        # Get market data feed
        if not isinstance(market_data, MarketDataFeed):
            logger.warning("⚠️ Market data should be MarketDataFeed instance")
            return signals
        
        instrument = 'XAU_USD'
        
        # Check if we have enough price history
        price_history = market_data.get_price_history(instrument, self.trend_period)
        if len(price_history) < self.trend_period:
            logger.debug(f"⏰ Not enough history for {instrument}: {len(price_history)} < {self.trend_period}")
            return signals
        
        # Get current price
        current_price_data = market_data.get_current_price(instrument)
        if not current_price_data:
            return signals
        
        current_price = (current_price_data.bid + current_price_data.ask) / 2
        
        # Get close prices
        close_prices = market_data.get_close_prices(instrument, self.trend_period)
        
        # Determine trend direction
        recent_prices = close_prices[-self.trend_period:]
        trend_momentum = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        
        # Need significant trend
        if abs(trend_momentum) < 0.001:  # Less than 0.1% trend
            logger.debug(f"⏰ Skipping {instrument}: trend too weak ({trend_momentum:.4f})")
            return signals
        
        # Get recent high/low for pullback detection
        lookback_prices = close_prices[-self.lookback_period:]
        recent_high = max(lookback_prices)
        recent_low = min(lookback_prices)
        
        # Calculate ATR for stop loss/take profit
        atr = market_data.calculate_atr(instrument, period=14)
        if not atr or atr == 0:
            logger.debug(f"⏰ Skipping {instrument}: ATR unavailable")
            return signals
        
        # Scalping: tight stops and quick profits
        stop_distance = atr * 1.0  # 1 ATR stop (tight)
        take_profit_distance = atr * 2.5  # 2.5 ATR target (1:2.5 R:R)
        
        # Detect pullback in uptrend (BUY signal)
        if trend_momentum > 0:
            # Check if price pulled back from recent high
            pullback_from_high = (recent_high - current_price) / recent_high
            
            if pullback_from_high >= self.pullback_depth_pct:
                # Pullback detected - BUY signal
                entry_price = current_price_data.ask
                stop_loss = entry_price - stop_distance
                take_profit = entry_price + take_profit_distance
                
                # Confidence based on pullback depth and trend strength
                confidence = min(0.9, self.min_confidence + (pullback_from_high / self.pullback_depth_pct) * 0.3)
                
                signal = TradeSignal(
                    instrument=instrument,
                    side='BUY',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    confidence=confidence,
                    strategy_name=self.name,
                    timestamp=datetime.utcnow()
                )
                
                signals.append(signal)
                logger.info(f"📊 {instrument} BUY signal (scalping): pullback={pullback_from_high:.4f}, confidence={confidence:.2f}")
        
        # Detect pullback in downtrend (SELL signal)
        elif trend_momentum < 0:
            # Check if price pulled back from recent low
            pullback_from_low = (current_price - recent_low) / recent_low
            
            if pullback_from_low >= self.pullback_depth_pct:
                # Pullback detected - SELL signal
                entry_price = current_price_data.bid
                stop_loss = entry_price + stop_distance
                take_profit = entry_price - take_profit_distance
                
                # Confidence based on pullback depth and trend strength
                confidence = min(0.9, self.min_confidence + (pullback_from_low / self.pullback_depth_pct) * 0.3)
                
                signal = TradeSignal(
                    instrument=instrument,
                    side='SELL',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    confidence=confidence,
                    strategy_name=self.name,
                    timestamp=datetime.utcnow()
                )
                
                signals.append(signal)
                logger.info(f"📊 {instrument} SELL signal (scalping): pullback={pullback_from_low:.4f}, confidence={confidence:.2f}")
        
        return signals

