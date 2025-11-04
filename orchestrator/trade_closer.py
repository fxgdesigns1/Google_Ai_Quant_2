#!/usr/bin/env python3
"""
Trade Closer Monitor
Monitors closed trades and updates adaptive learning system
"""

import threading
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TradeCloser:
    """Monitor closed trades and update adaptive learning"""
    
    def __init__(self, broker, trade_logger, adaptive_learning, accounts: List[Dict]):
        """Initialize trade closer"""
        self.broker = broker
        self.trade_logger = trade_logger
        self.adaptive_learning = adaptive_learning
        self.accounts = accounts
        
        # Track which trades we've already processed
        self.processed_trades: Dict[str, bool] = {}
        
        # Running state
        self.running = False
        self.monitor_thread: threading.Thread = None
        
        logger.info("✅ Trade Closer initialized")
    
    def start(self, check_interval: int = 60):
        """Start monitoring closed trades"""
        if self.running:
            logger.warning("Trade closer already running")
            return
        
        self.running = True
        self.check_interval = check_interval
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"✅ Trade closer started (check interval: {check_interval}s)")
    
    def stop(self):
        """Stop trade closer"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        logger.info("✅ Trade closer stopped")
    
    def _monitor_loop(self):
        """Monitor closed trades"""
        logger.info("🔄 Starting trade closer monitoring loop")
        
        while self.running:
            try:
                for account in self.accounts:
                    if not account.get('enabled', False):
                        continue
                    
                    account_id = account.get('id')
                    if not account_id:
                        continue
                    
                    try:
                        # Get recent closed trades from database
                        if self.trade_logger:
                            recent_trades = self.trade_logger.get_recent_trades(
                                limit=100,
                                account_id=account_id
                            )
                            
                            for trade in recent_trades:
                                trade_id = trade.get('trade_id')
                                if not trade_id:
                                    continue
                                
                                # Check if already processed
                                if trade_id in self.processed_trades:
                                    continue
                                
                                # Only process closed trades
                                if trade.get('status') != 'CLOSED':
                                    continue
                                
                                # Track for adaptive learning
                                if self.adaptive_learning:
                                    instrument = trade.get('instrument')
                                    strategy_name = trade.get('strategy_name')
                                    pnl = trade.get('pnl', 0.0)
                                    pnl_pct = trade.get('pnl_pct', 0.0)
                                    
                                    if instrument and strategy_name:
                                        self.adaptive_learning.track_trade(
                                            instrument=instrument,
                                            strategy_name=strategy_name,
                                            pnl=pnl,
                                            pnl_pct=pnl_pct
                                        )
                                        
                                        # Try to optimize if enough data
                                        if self.adaptive_learning.should_optimize(instrument):
                                            self.adaptive_learning.optimize_parameters(instrument)
                                
                                # Mark as processed
                                self.processed_trades[trade_id] = True
                    
                    except Exception as e:
                        logger.debug(f"Error monitoring account {account_id}: {e}")
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in trade closer loop: {e}", exc_info=True)
                time.sleep(60)

