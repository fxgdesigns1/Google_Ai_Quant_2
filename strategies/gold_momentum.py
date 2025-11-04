#!/usr/bin/env python3
"""
Gold Momentum Strategy
Trend-following strategy for XAU_USD that ALWAYS trades WITH the trend
"""

import logging
from typing import List, Dict
from datetime import datetime

from .base_strategy import BaseStrategy
from core.order_executor import TradeSignal
from core.market_data import MarketDataFeed

logger = logging.getLogger(__name__)


class GoldMomentumStrategy(BaseStrategy):
    """Momentum-based trend-following strategy for Gold"""
    
    def __init__(self, config: Dict):
        """Initialize gold momentum strategy"""
        super().__init__(config)
        
        # Strategy parameters
        self.min_momentum = config.get('min_momentum', 0.0015)  # 0.15% minimum momentum
        self.momentum_period = config.get('momentum_period', 50)  # 50 bars = ~4 hours
        self.trend_period = config.get('trend_period', 100)  # 100 bars = ~8 hours
        self.min_adx = config.get('min_adx', 15.0)  # Minimum ADX for trend strength
        self.min_confidence = config.get('min_confidence', 0.35)  # 35% minimum confidence
        
        logger.info(f"✅ Gold Momentum Strategy initialized")
        logger.info(f"   Min momentum: {self.min_momentum}")
        logger.info(f"   Momentum period: {self.momentum_period} bars")
        logger.info(f"   Trend period: {self.trend_period} bars")
    
    def analyze(self, market_data: Dict) -> List[TradeSignal]:
        """Analyze market data and generate trade signals"""
        signals = []
        
        if not self.enabled:
            return signals
        
        # This strategy only trades XAU_USD
        if 'XAU_USD' not in self.instruments:
            return signals
        
        # Get market data feed (should be passed in)
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
        
        # Get close prices for calculations
        close_prices = market_data.get_close_prices(instrument, self.trend_period)
        
        # Calculate short-term momentum (50 bars)
        if len(close_prices) < self.momentum_period:
            return signals
        
        recent_prices = close_prices[-self.momentum_period:]
        momentum = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        
        # Calculate longer-term trend (100 bars)
        trend_prices = close_prices[-self.trend_period:]
        trend_momentum = (trend_prices[-1] - trend_prices[0]) / trend_prices[0]
        
        # CRITICAL: Only trade WITH the trend, not against it
        # If trend and momentum disagree, skip the trade
        if (momentum > 0 and trend_momentum < -0.001) or (momentum < 0 and trend_momentum > 0.001):
            logger.debug(f"⏰ Skipping {instrument}: momentum and trend disagree (momentum={momentum:.4f}, trend={trend_momentum:.4f})")
            return signals
        
        # Check momentum threshold
        if abs(momentum) < self.min_momentum:
            logger.debug(f"⏰ Skipping {instrument}: momentum too weak ({momentum:.4f} < {self.min_momentum})")
            return signals
        
        # Calculate ATR for stop loss/take profit
        atr = market_data.calculate_atr(instrument, period=14)
        if not atr or atr == 0:
            logger.debug(f"⏰ Skipping {instrument}: ATR unavailable")
            return signals
        
        # Determine direction based on momentum
        if momentum > 0:
            # Bullish momentum - BUY
            side = 'BUY'
            entry_price = current_price_data.ask
            stop_loss = entry_price - (atr * 2.5)  # 2.5 ATR stop
            take_profit = entry_price + (atr * 20.0)  # 20 ATR target (1:8 R:R)
            
            # Confidence based on momentum strength and trend alignment
            confidence = min(0.95, self.min_confidence + (momentum / self.min_momentum) * 0.3)
            
            signal = TradeSignal(
                instrument=instrument,
                side=side,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence,
                strategy_name=self.name,
                timestamp=datetime.utcnow()
            )
            
            signals.append(signal)
            logger.info(f"📊 {instrument} BUY signal: momentum={momentum:.4f}, confidence={confidence:.2f}")
            
        elif momentum < 0:
            # Bearish momentum - SELL
            side = 'SELL'
            entry_price = current_price_data.bid
            stop_loss = entry_price + (atr * 2.5)  # 2.5 ATR stop
            take_profit = entry_price - (atr * 20.0)  # 20 ATR target (1:8 R:R)
            
            # Confidence based on momentum strength and trend alignment
            confidence = min(0.95, self.min_confidence + (abs(momentum) / self.min_momentum) * 0.3)
            
            signal = TradeSignal(
                instrument=instrument,
                side=side,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence,
                strategy_name=self.name,
                timestamp=datetime.utcnow()
            )
            
            signals.append(signal)
            logger.info(f"📊 {instrument} SELL signal: momentum={momentum:.4f}, confidence={confidence:.2f}")
        
        return signals
