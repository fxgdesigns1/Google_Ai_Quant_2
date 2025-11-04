#!/usr/bin/env python3
"""
Strategy Coordinator
Runs all strategies in parallel and collects trade signals
"""

import threading
import time
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class StrategyCoordinator:
    """Coordinate multiple trading strategies"""
    
    def __init__(self, strategies: List, market_data, order_executor, risk_manager, config: Dict = None):
        """Initialize strategy coordinator"""
        self.strategies = strategies
        self.market_data = market_data
        self.order_executor = order_executor
        self.risk_manager = risk_manager
        self.config = config or {}
        
        # Signal collection
        self.signals: List = []
        self.signal_lock = threading.Lock()
        
        # Account mapping (strategy name -> account config)
        # Map by strategy instance name (which comes from account name)
        self.account_map = {}
        if config:
            for account in config.get('accounts', []):
                account_name = account.get('name')
                if account_name:
                    self.account_map[account_name] = account
        
        # Running state
        self.running = False
        self.scan_thread: threading.Thread = None
        
        logger.info(f"✅ Strategy Coordinator initialized with {len(strategies)} strategies")
    
    def start(self, scan_interval: int = 300):
        """Start the strategy coordinator (scan every 5 minutes)"""
        if self.running:
            logger.warning("Strategy coordinator already running")
            return
        
        self.running = True
        self.scan_interval = scan_interval
        self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.scan_thread.start()
        logger.info(f"✅ Strategy coordinator started (scan interval: {scan_interval}s)")
    
    def stop(self):
        """Stop the strategy coordinator"""
        self.running = False
        if self.scan_thread:
            self.scan_thread.join(timeout=10)
        logger.info("✅ Strategy coordinator stopped")
    
    def _scan_loop(self):
        """Main scanning loop"""
        logger.info("🔄 Starting strategy scan loop")
        
        while self.running:
            try:
                # Run all strategies and collect signals
                all_signals = []
                
                for strategy in self.strategies:
                    if not strategy.is_enabled():
                        continue
                    
                    try:
                        signals = strategy.analyze(self.market_data)
                        all_signals.extend(signals)
                        logger.debug(f"✅ {strategy.get_name()}: {len(signals)} signals")
                    except Exception as e:
                        logger.error(f"❌ Error running strategy {strategy.get_name()}: {e}", exc_info=True)
                
                # Store signals
                with self.signal_lock:
                    self.signals = all_signals
                
                logger.info(f"📊 Total signals generated: {len(all_signals)}")
                
                # Execute trades for each signal
                for signal in all_signals:
                    try:
                        # Find account for this strategy
                        account_config = self.account_map.get(signal.strategy_name)
                        if not account_config:
                            logger.warning(f"⚠️ No account found for strategy: {signal.strategy_name}")
                            continue
                        
                        account_id = account_config.get('id')
                        if not account_id:
                            continue
                        
                        # Get account balance and positions
                        account = self.order_executor.broker.get_account(account_id)
                        current_positions = self.order_executor.broker.get_open_trades(account_id)
                        
                        # Convert positions to dict format
                        positions_list = []
                        for pos in current_positions:
                            positions_list.append({
                                'instrument': pos.get('instrument'),
                                'units': pos.get('currentUnits'),
                                'side': 'BUY' if int(pos.get('currentUnits', 0)) > 0 else 'SELL'
                            })
                        
                        # Get risk per trade from account config
                        risk_per_trade = account_config.get('risk', {}).get('max_risk_per_trade', 0.01)
                        
                        # Check daily trade limit
                        daily_limit = account_config.get('risk', {}).get('daily_trade_limit', 10)
                        can_trade, reason = self.risk_manager.check_daily_trade_limit(account_id, daily_limit)
                        if not can_trade:
                            logger.debug(f"⏸️ Daily trade limit reached for {account_id}: {reason}")
                            continue
                        
                        # Execute trade
                        execution = self.order_executor.execute_trade(
                            signal=signal,
                            account_id=account_id,
                            account_balance=account.balance,
                            current_positions=positions_list,
                            risk_per_trade_pct=risk_per_trade
                        )
                        
                        if execution.success:
                            logger.info(f"✅ Trade executed: {signal.instrument} {signal.side}")
                        else:
                            logger.debug(f"⏸️ Trade rejected: {execution.error_message}")
                    
                    except Exception as e:
                        logger.error(f"❌ Error executing signal: {e}", exc_info=True)
                
                # Wait before next scan
                time.sleep(self.scan_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in scan loop: {e}", exc_info=True)
                time.sleep(60)  # Wait before retrying
    
    def get_signals(self) -> List:
        """Get current signals"""
        with self.signal_lock:
            return self.signals.copy()
    
    def get_strategy_status(self) -> Dict:
        """Get status of all strategies"""
        status = {}
        for strategy in self.strategies:
            status[strategy.get_name()] = {
                'enabled': strategy.is_enabled(),
                'instruments': strategy.get_instruments()
            }
        return status
