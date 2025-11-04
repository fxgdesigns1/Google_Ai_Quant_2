#!/usr/bin/env python3
"""
GBP/USD Momentum Strategy
Momentum-based trend-following strategy for GBP/USD
"""

import logging
from typing import List, Dict
from datetime import datetime

from .base_strategy import BaseStrategy
from core.order_executor import TradeSignal
from core.market_data import MarketDataFeed

logger = logging.getLogger(__name__)


class GbpUsdMomentumStrategy(BaseStrategy):
    """Momentum-based trend-following strategy for GBP/USD"""
    
    def __init__(self, config: Dict):
        """Initialize GBP/USD momentum strategy"""
        super().__init__(config)
        
        # Strategy parameters
        self.fast_period = config.get('fast_period', 8)  # Fast EMA
        self.slow_period = config.get('slow_period', 21)  # Slow EMA
        self.momentum_period = config.get('momentum_period', 50)  # Momentum period
        self.min_momentum = config.get('min_momentum', 0.0008)  # 0.08% minimum momentum
        self.min_confidence = config.get('min_confidence', 0.35)  # 35% minimum confidence
        
        logger.info(f"✅ GBP/USD Momentum Strategy initialized")
        logger.info(f"   Fast EMA: {self.fast_period}, Slow EMA: {self.slow_period}")
        logger.info(f"   Momentum period: {self.momentum_period} bars")
    
    def analyze(self, market_data: Dict) -> List[TradeSignal]:
        """Analyze market data and generate trade signals"""
        signals = []
        
        if not self.enabled:
            return signals
        
        # This strategy only trades GBP_USD
        if 'GBP_USD' not in self.instruments:
            return signals
        
        # Get market data feed
        if not isinstance(market_data, MarketDataFeed):
            logger.warning("⚠️ Market data should be MarketDataFeed instance")
            return signals
        
        instrument = 'GBP_USD'
        
        # Check if we have enough price history
        price_history = market_data.get_price_history(instrument, self.momentum_period)
        if len(price_history) < self.momentum_period:
            logger.debug(f"⏰ Not enough history for {instrument}: {len(price_history)} < {self.momentum_period}")
            return signals
        
        # Get current price
        current_price_data = market_data.get_current_price(instrument)
        if not current_price_data:
            return signals
        
        current_price = (current_price_data.bid + current_price_data.ask) / 2
        
        # Get close prices
        close_prices = market_data.get_close_prices(instrument, self.momentum_period)
        
        # Calculate EMAs
        fast_ema = market_data.calculate_ema(instrument, period=self.fast_period)
        slow_ema = market_data.calculate_ema(instrument, period=self.slow_period)
        
        if not fast_ema or not slow_ema:
            logger.debug(f"⏰ Skipping {instrument}: EMAs unavailable")
            return signals
        
        # Calculate momentum
        recent_prices = close_prices[-self.momentum_period:]
        momentum = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        
        # Check momentum threshold
        if abs(momentum) < self.min_momentum:
            logger.debug(f"⏰ Skipping {instrument}: momentum too weak ({momentum:.4f} < {self.min_momentum})")
            return signals
        
        # Calculate ATR for stop loss/take profit
        atr = market_data.calculate_atr(instrument, period=14)
        if not atr or atr == 0:
            logger.debug(f"⏰ Skipping {instrument}: ATR unavailable")
            return signals
        
        # Determine direction based on EMA crossover and momentum
        # BUY: Fast EMA > Slow EMA AND momentum > 0
        # SELL: Fast EMA < Slow EMA AND momentum < 0
        
        # CRITICAL: Only trade when EMA alignment matches momentum direction
        if fast_ema > slow_ema and momentum > 0:
            # Bullish setup - BUY signal
            side = 'BUY'
            entry_price = current_price_data.ask
            stop_loss = entry_price - (atr * 2.0)  # 2 ATR stop
            take_profit = entry_price + (atr * 6.0)  # 6 ATR target (1:3 R:R)
            
            # Confidence based on momentum strength and EMA spread
            ema_spread = (fast_ema - slow_ema) / slow_ema
            confidence = min(0.95, self.min_confidence + (momentum / self.min_momentum) * 0.3 + min(ema_spread * 100, 0.2))
            
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
            
        elif fast_ema < slow_ema and momentum < 0:
            # Bearish setup - SELL signal
            side = 'SELL'
            entry_price = current_price_data.bid
            stop_loss = entry_price + (atr * 2.0)  # 2 ATR stop
            take_profit = entry_price - (atr * 6.0)  # 6 ATR target (1:3 R:R)
            
            # Confidence based on momentum strength and EMA spread
            ema_spread = (slow_ema - fast_ema) / fast_ema
            confidence = min(0.95, self.min_confidence + (abs(momentum) / self.min_momentum) * 0.3 + min(ema_spread * 100, 0.2))
            
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

