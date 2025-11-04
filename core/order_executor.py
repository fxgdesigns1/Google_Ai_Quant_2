#!/usr/bin/env python3
"""
Order Executor
Execute approved trades with broker, including position sizing and trade confirmation
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .broker_api import OandaBroker, BrokerOrder, BrokerAccount
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)

# Optional imports for Telegram and logging
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from monitoring.telegram_alerts import TelegramAlerts
    from database.trade_logger import TradeLogger
    TELEGRAM_AVAILABLE = True
    LOGGER_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    LOGGER_AVAILABLE = False


@dataclass
class TradeSignal:
    """Trading signal from strategy"""
    instrument: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    confidence: float
    strategy_name: str
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class TradeExecution:
    """Trade execution result"""
    signal: TradeSignal
    order: Optional[BrokerOrder]
    success: bool
    error_message: Optional[str] = None
    execution_time: datetime = None
    
    def __post_init__(self):
        if self.execution_time is None:
            self.execution_time = datetime.utcnow()


class OrderExecutor:
    """Order execution engine"""
    
    def __init__(
        self,
        broker: OandaBroker,
        risk_manager: RiskManager,
        telegram_alerts: Optional[TelegramAlerts] = None,
        trade_logger: Optional[TradeLogger] = None,
        position_manager = None,
        adaptive_learning = None
    ):
        """Initialize order executor"""
        self.broker = broker
        self.risk_manager = risk_manager
        self.telegram_alerts = telegram_alerts if TELEGRAM_AVAILABLE else None
        self.trade_logger = trade_logger if LOGGER_AVAILABLE else None
        self.position_manager = position_manager
        self.adaptive_learning = adaptive_learning
        
        # Execution history
        self.execution_history: List[TradeExecution] = []
        
        logger.info("✅ Order Executor initialized")
        if self.telegram_alerts:
            logger.info("   Telegram alerts enabled")
        if self.trade_logger:
            logger.info("   Trade logging enabled")
        if self.adaptive_learning:
            logger.info("   Adaptive learning enabled")
    
    def calculate_position_size(
        self,
        account_balance: float,
        instrument: str,
        entry_price: float,
        stop_loss: float,
        risk_per_trade_pct: float
    ) -> Tuple[int, float, float]:
        """
        Calculate position size based on risk
        
        Returns:
            (units, position_value, risk_amount)
        """
        
        # Calculate risk amount in account currency
        risk_amount = account_balance * risk_per_trade_pct
        
        # Calculate stop loss distance in price terms
        stop_distance = abs(entry_price - stop_loss)
        
        if stop_distance == 0:
            logger.warning(f"⚠️ Stop loss equals entry price for {instrument}")
            return 0, 0.0, 0.0
        
        # For Gold (XAU_USD), pip value is $10 per unit per dollar movement
        # For forex pairs, pip value depends on quote currency
        # Simplified: assume 1 unit = 1 pip movement for most pairs
        # For Gold: 1 unit = $1 price movement
        
        if instrument == 'XAU_USD':
            # Gold: $10 per unit per $1 move
            pip_value_per_unit = 10.0
            units = int((risk_amount / stop_distance) / pip_value_per_unit)
        else:
            # Forex: assume 0.0001 = 1 pip for most pairs
            # For JPY pairs, 0.01 = 1 pip
            pip_size = 0.0001 if 'JPY' not in instrument else 0.01
            pip_distance = stop_distance / pip_size
            pip_value_per_unit = 10.0  # Standard lot pip value
            units = int((risk_amount / pip_distance) / pip_value_per_unit * 10000)
        
        # Round to nearest valid lot size
        # OANDA minimum: 1 unit for most instruments
        units = max(1, units)
        
        # Calculate position value
        position_value = units * entry_price
        
        # Recalculate actual risk based on rounded units
        if instrument == 'XAU_USD':
            actual_risk = units * pip_value_per_unit * stop_distance
        else:
            pip_size = 0.0001 if 'JPY' not in instrument else 0.01
            pip_distance = stop_distance / pip_size
            actual_risk = (units / 10000) * pip_value_per_unit * pip_distance
        
        return units, position_value, actual_risk
    
    def execute_trade(
        self,
        signal: TradeSignal,
        account_id: str,
        account_balance: float,
        current_positions: List[Dict],
        risk_per_trade_pct: float
    ) -> TradeExecution:
        """
        Execute a trade signal
        
        Steps:
        1. Get current account info
        2. Calculate position size
        3. Run risk checks
        4. Place order with broker
        5. Confirm execution
        6. Log trade
        """
        
        try:
            # Get current account info
            account = self.broker.get_account(account_id)
            
            # Get current price for entry
            current_price_data = self.broker.get_prices([signal.instrument], account_id)
            if signal.instrument not in current_price_data:
                return TradeExecution(
                    signal=signal,
                    order=None,
                    success=False,
                    error_message=f"Could not get current price for {signal.instrument}"
                )
            
            price_data = current_price_data[signal.instrument]
            entry_price = price_data.ask if signal.side == 'BUY' else price_data.bid
            
            # Calculate stop loss if not provided
            if signal.stop_loss is None:
                # Default: 20 pips for forex, 10 pips for gold
                if signal.instrument == 'XAU_USD':
                    stop_distance = 10.0  # $10 stop for gold
                else:
                    pip_size = 0.0001 if 'JPY' not in signal.instrument else 0.01
                    stop_distance = 20 * pip_size
                
                signal.stop_loss = entry_price - stop_distance if signal.side == 'BUY' else entry_price + stop_distance
            
            # Calculate position size
            units, position_value, risk_amount = self.calculate_position_size(
                account_balance=account.balance,
                instrument=signal.instrument,
                entry_price=entry_price,
                stop_loss=signal.stop_loss,
                risk_per_trade_pct=risk_per_trade_pct
            )
            
            # Convert side to units sign
            # Positive units = long, negative units = short
            if signal.side == 'SELL':
                units = -units
            
            # Calculate spread in pips
            spread_pips = (price_data.spread / price_data.bid) * 10000 if price_data.bid > 0 else 999
            if 'JPY' in signal.instrument:
                spread_pips = (price_data.spread / price_data.bid) * 100
            
            # Run risk checks
            can_open, reason = self.risk_manager.can_open_position(
                account_id=account_id,
                account_balance=account.balance,
                instrument=signal.instrument,
                signal_confidence=signal.confidence,
                spread_pips=spread_pips,
                current_positions=current_positions,
                margin_used=account.margin_used,
                margin_available=account.margin_available,
                position_size_value=position_value,
                risk_amount=risk_amount
            )
            
            if not can_open:
                logger.warning(f"⏸️ Trade rejected: {reason}")
                
                # Log rejected signal
                if self.trade_logger:
                    try:
                        self.trade_logger.log_signal(signal, status='REJECTED', reason=reason)
                    except Exception as e:
                        logger.debug(f"Failed to log rejected signal: {e}")
                
                return TradeExecution(
                    signal=signal,
                    order=None,
                    success=False,
                    error_message=reason
                )
            
            # Place order with broker
            logger.info(f"📤 Placing order: {signal.instrument} {signal.side} {abs(units)} units @ {entry_price:.5f}")
            
            order = self.broker.place_market_order(
                instrument=signal.instrument,
                units=units,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                account_id=account_id
            )
            
            # Confirm execution
            if order.status == 'FILLED' or order.trade_id:
                logger.info(f"✅ Trade executed: {signal.instrument} {signal.side} {abs(units)} units")
                
                # Increment trade count
                self.risk_manager.increment_trade_count(account_id)
                
                execution = TradeExecution(
                    signal=signal,
                    order=order,
                    success=True,
                    error_message=None
                )
                self.execution_history.append(execution)
                
                # Log trade to database
                if self.trade_logger and order.trade_id:
                    try:
                        self.trade_logger.log_trade({
                            'trade_id': order.trade_id,
                            'account_id': account_id,
                            'instrument': signal.instrument,
                            'side': signal.side,
                            'units': abs(units),
                            'entry_price': entry_price,
                            'stop_loss': signal.stop_loss,
                            'take_profit': signal.take_profit,
                            'exit_price': None,
                            'pnl': 0.0,
                            'pnl_pct': 0.0,
                            'strategy_name': signal.strategy_name,
                            'entry_time': datetime.utcnow(),
                            'exit_time': None,
                            'duration_minutes': None,
                            'status': 'OPEN'
                        })
                    except Exception as e:
                        logger.error(f"❌ Failed to log trade: {e}")
                
                # Send Telegram alert
                if self.telegram_alerts and order.trade_id:
                    try:
                        self.telegram_alerts.send_trade_opened(
                            account_id=account_id,
                            instrument=signal.instrument,
                            side=signal.side,
                            units=abs(units),
                            entry_price=entry_price,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                            strategy_name=signal.strategy_name
                        )
                    except Exception as e:
                        logger.debug(f"Failed to send Telegram alert: {e}")
                
                # Register trade with position manager
                if self.position_manager and order.trade_id:
                    try:
                        self.position_manager.register_trade(
                            trade_id=order.trade_id,
                            account_id=account_id,
                            instrument=signal.instrument,
                            entry_price=entry_price,
                            side=signal.side
                        )
                    except Exception as e:
                        logger.debug(f"Failed to register trade with position manager: {e}")
                
                return execution
            else:
                error_msg = f"Order not filled: {order.status}"
                logger.error(f"❌ {error_msg}")
                return TradeExecution(
                    signal=signal,
                    order=order,
                    success=False,
                    error_message=error_msg
                )
                
        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}", exc_info=True)
            return TradeExecution(
                signal=signal,
                order=None,
                success=False,
                error_message=str(e)
            )
    
    def close_position(
        self,
        trade_id: str,
        account_id: str
    ) -> bool:
        """Close a position by trade ID"""
        try:
            self.broker.close_trade(trade_id, account_id)
            logger.info(f"✅ Position closed: {trade_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to close position {trade_id}: {e}")
            return False
    
    def get_execution_history(self, limit: int = 100) -> List[TradeExecution]:
        """Get recent execution history"""
        return self.execution_history[-limit:]
