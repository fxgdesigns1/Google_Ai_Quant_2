#!/usr/bin/env python3
"""
Risk Management Engine
Enforces ALL risk rules before any trade, including circuit breaker and concentration limits
"""

import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Optional Telegram import
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from monitoring.telegram_alerts import TelegramAlerts
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


@dataclass
class RiskLimits:
    """Risk limit configuration"""
    max_risk_per_trade: float = 0.02  # 2% per trade
    max_portfolio_risk: float = 0.75  # 75% total exposure
    max_positions: int = 20
    max_positions_per_instrument: int = 3
    max_correlated_pairs: int = 2
    max_spread_pips: float = 3.0
    min_signal_confidence: float = 0.7
    circuit_breaker_loss_pct: float = 2.0  # Stop all trading if lose 2% in one day
    max_exposure_per_instrument_pct: float = 30.0  # 30% max exposure per instrument


class RiskManager:
    """Comprehensive risk management engine"""
    
    # Correlation groups
    CORRELATION_GROUPS = {
        'EUR_PAIRS': ['EUR_USD', 'EUR_JPY', 'EUR_GBP', 'EUR_AUD', 'EUR_CAD'],
        'GBP_PAIRS': ['GBP_USD', 'GBP_JPY', 'EUR_GBP', 'GBP_AUD', 'GBP_CAD'],
        'JPY_PAIRS': ['USD_JPY', 'EUR_JPY', 'GBP_JPY', 'AUD_JPY', 'CAD_JPY'],
        'USD_PAIRS': ['EUR_USD', 'GBP_USD', 'USD_JPY', 'AUD_USD', 'USD_CAD', 'NZD_USD'],
        'COMMODITY': ['XAU_USD', 'XAG_USD', 'USD_CAD', 'AUD_USD', 'NZD_USD']
    }
    
    # Trading sessions (UTC)
    LONDON_SESSION = (time(7, 0), time(16, 0))   # 07:00-16:00 UTC
    NY_SESSION = (time(13, 0), time(21, 0))      # 13:00-21:00 UTC
    
    def __init__(self, limits: RiskLimits = None, telegram_alerts: Optional[TelegramAlerts] = None, news_aggregator = None):
        """Initialize risk manager"""
        self.limits = limits or RiskLimits()
        self.telegram_alerts = telegram_alerts if TELEGRAM_AVAILABLE else None
        self.news_aggregator = news_aggregator
        
        # Daily tracking for circuit breaker
        self.daily_start_balance: Dict[str, float] = {}
        self.daily_trade_count: Dict[str, int] = {}
        self.last_reset_date: Dict[str, datetime] = {}
        
        # Circuit breaker state
        self.circuit_breaker_triggered: Dict[str, bool] = {}
        
        logger.info("✅ Risk Manager initialized")
        logger.info(f"   Max positions: {self.limits.max_positions}")
        logger.info(f"   Max positions per instrument: {self.limits.max_positions_per_instrument}")
        logger.info(f"   Circuit breaker: {self.limits.circuit_breaker_loss_pct}% daily loss")
        if self.telegram_alerts:
            logger.info("   Telegram alerts enabled")
    
    def reset_daily_tracking(self, account_id: str, current_balance: float):
        """Reset daily tracking at start of trading day"""
        today = datetime.utcnow().date()
        
        if account_id not in self.last_reset_date or self.last_reset_date[account_id].date() != today:
            self.daily_start_balance[account_id] = current_balance
            self.daily_trade_count[account_id] = 0
            self.last_reset_date[account_id] = datetime.utcnow()
            self.circuit_breaker_triggered[account_id] = False
            logger.info(f"✅ Daily tracking reset for account {account_id}")
    
    def check_circuit_breaker(self, account_id: str, current_balance: float) -> Tuple[bool, str]:
        """Check if circuit breaker should trigger"""
        self.reset_daily_tracking(account_id, current_balance)
        
        if self.circuit_breaker_triggered.get(account_id, False):
            return False, "Circuit breaker already triggered - trading stopped"
        
        start_balance = self.daily_start_balance.get(account_id, current_balance)
        daily_pl_pct = (current_balance - start_balance) / start_balance * 100
        
        if daily_pl_pct <= -self.limits.circuit_breaker_loss_pct:
            self.circuit_breaker_triggered[account_id] = True
            logger.error(f"🔴 CIRCUIT BREAKER TRIGGERED for account {account_id}: {daily_pl_pct:.2f}% loss")
            
            # Send Telegram alert
            if self.telegram_alerts:
                try:
                    self.telegram_alerts.send_circuit_breaker_alert(
                        account_id=account_id,
                        daily_loss_pct=abs(daily_pl_pct),
                        current_balance=current_balance
                    )
                except Exception as e:
                    logger.debug(f"Failed to send circuit breaker alert: {e}")
            
            return False, f"Circuit breaker triggered: {daily_pl_pct:.2f}% daily loss"
        
        return True, "OK"
    
    def reset_circuit_breaker(self, account_id: str):
        """Manually reset circuit breaker (requires explicit action)"""
        self.circuit_breaker_triggered[account_id] = False
        logger.info(f"✅ Circuit breaker reset for account {account_id}")
    
    def can_open_position(
        self,
        account_id: str,
        account_balance: float,
        instrument: str,
        signal_confidence: float,
        spread_pips: float,
        current_positions: List[Dict[str, any]],
        margin_used: float,
        margin_available: float,
        position_size_value: float,
        risk_amount: float
    ) -> Tuple[bool, str]:
        """
        Comprehensive pre-trade risk check
        
        Returns:
            (can_open: bool, reason: str)
        """
        
        # Check 1: Circuit breaker
        can_trade, reason = self.check_circuit_breaker(account_id, account_balance)
        if not can_trade:
            return False, reason
        
        # Check 2: Signal confidence
        if signal_confidence < self.limits.min_signal_confidence:
            return False, f"Signal confidence too low: {signal_confidence:.2f} < {self.limits.min_signal_confidence}"
        
        # Check 3: Spread filter
        if spread_pips > self.limits.max_spread_pips:
            return False, f"Spread too wide: {spread_pips:.1f} pips > {self.limits.max_spread_pips} pips"
        
        # Check 4: Total positions limit
        if len(current_positions) >= self.limits.max_positions:
            return False, f"Max positions reached: {len(current_positions)}/{self.limits.max_positions}"
        
        # Check 5: Positions per instrument
        positions_on_instrument = [p for p in current_positions if p.get('instrument') == instrument]
        if len(positions_on_instrument) >= self.limits.max_positions_per_instrument:
            return False, f"Max positions per instrument reached: {len(positions_on_instrument)}/{self.limits.max_positions_per_instrument}"
        
        # Check 6: Margin available
        margin_used_pct = (margin_used / account_balance) * 100 if account_balance > 0 else 100
        if margin_used_pct >= self.limits.max_portfolio_risk * 100:
            return False, f"Margin limit reached: {margin_used_pct:.1f}% >= {self.limits.max_portfolio_risk * 100}%"
        
        # Check 7: Position size value vs account
        exposure_pct = (position_size_value / account_balance) * 100 if account_balance > 0 else 100
        if exposure_pct > self.limits.max_exposure_per_instrument_pct:
            return False, f"Exposure too high: {exposure_pct:.1f}% > {self.limits.max_exposure_per_instrument_pct}%"
        
        # Check 8: Risk per trade
        risk_pct = (risk_amount / account_balance) * 100 if account_balance > 0 else 100
        if risk_pct > self.limits.max_risk_per_trade * 100:
            return False, f"Risk per trade too high: {risk_pct:.2f}% > {self.limits.max_risk_per_trade * 100}%"
        
        # Check 9: Correlation check
        open_instruments = [p.get('instrument') for p in current_positions]
        correlated_count = self._count_correlated_pairs(instrument, open_instruments)
        if correlated_count >= self.limits.max_correlated_pairs:
            return False, f"Too many correlated pairs: {correlated_count}/{self.limits.max_correlated_pairs}"
        
        # Check 10: Trading hours
        if not self.is_trading_hours():
            return False, "Outside trading hours (London/NY sessions only)"
        
        # Check 11: News-based trading halt (if news aggregator available)
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from intelligence.news_aggregator import NewsAggregator
            
            # Check if news aggregator should pause trading
            # Note: news_aggregator needs to be passed in or created here
            # For now, we'll check if it's available via a module-level instance
            if hasattr(self, 'news_aggregator') and self.news_aggregator:
                should_pause, reason = self.news_aggregator.should_pause_trading(instrument)
                if should_pause:
                    return False, reason
        except Exception as e:
            logger.debug(f"News check failed: {e}")
        
        # Check 12: Margin available for new position
        required_margin = position_size_value * 0.01  # Approximate margin requirement (1%)
        if margin_available < required_margin:
            return False, f"Insufficient margin: {margin_available:.2f} < {required_margin:.2f}"
        
        return True, "All risk checks passed"
    
    def _count_correlated_pairs(self, instrument: str, open_instruments: List[str]) -> int:
        """Count how many correlated pairs are already open"""
        correlated_count = 0
        
        # Find which correlation groups this instrument belongs to
        instrument_groups = []
        for group_name, pairs in self.CORRELATION_GROUPS.items():
            if instrument in pairs:
                instrument_groups.append(group_name)
        
        # Count open positions in same groups
        for open_inst in open_instruments:
            for group_name in instrument_groups:
                if open_inst in self.CORRELATION_GROUPS.get(group_name, []):
                    correlated_count += 1
                    break  # Count each instrument once
        
        return correlated_count
    
    def is_trading_hours(self, current_time: Optional[datetime] = None) -> bool:
        """Check if current time is within trading hours (London or NY sessions)"""
        if current_time is None:
            current_time = datetime.utcnow()
        
        current_hour_minute = current_time.time()
        
        # Check London session (07:00-16:00 UTC)
        if self.LONDON_SESSION[0] <= current_hour_minute <= self.LONDON_SESSION[1]:
            return True
        
        # Check NY session (13:00-21:00 UTC)
        if self.NY_SESSION[0] <= current_hour_minute <= self.NY_SESSION[1]:
            return True
        
        return False
    
    def get_session_name(self, current_time: Optional[datetime] = None) -> str:
        """Get current trading session name"""
        if current_time is None:
            current_time = datetime.utcnow()
        
        current_hour_minute = current_time.time()
        
        # Check sessions
        if self.LONDON_SESSION[0] <= current_hour_minute <= self.LONDON_SESSION[1]:
            if self.NY_SESSION[0] <= current_hour_minute <= self.NY_SESSION[1]:
                return "LONDON+NY (Peak Liquidity)"
            return "LONDON"
        
        if self.NY_SESSION[0] <= current_hour_minute <= self.NY_SESSION[1]:
            return "NEW YORK"
        
        return "CLOSED"
    
    def increment_trade_count(self, account_id: str):
        """Increment daily trade count"""
        if account_id not in self.daily_trade_count:
            self.daily_trade_count[account_id] = 0
        self.daily_trade_count[account_id] += 1
    
    def get_daily_trade_count(self, account_id: str) -> int:
        """Get daily trade count"""
        return self.daily_trade_count.get(account_id, 0)
    
    def check_daily_trade_limit(self, account_id: str, daily_limit: int) -> Tuple[bool, str]:
        """Check if daily trade limit is reached"""
        count = self.get_daily_trade_count(account_id)
        if count >= daily_limit:
            return False, f"Daily trade limit reached: {count}/{daily_limit}"
        return True, "OK"
