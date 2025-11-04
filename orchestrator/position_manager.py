#!/usr/bin/env python3
"""
Position Manager
Manage positions, break-even stops, trailing stops
"""

import threading
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PositionManager:
    """Manage open positions and order modifications"""
    
    def __init__(self, broker, risk_manager, accounts: List[Dict] = None):
        """Initialize position manager"""
        self.broker = broker
        self.risk_manager = risk_manager
        self.accounts = accounts or []
        
        # Position tracking
        self.trade_entries: Dict[str, Dict] = {}  # trade_id -> entry info
        self.breakeven_moved: Dict[str, bool] = {}  # trade_id -> bool
        self.trailing_stops: Dict[str, float] = {}  # trade_id -> last trailing price
        
        # Running state
        self.running = False
        self.monitor_thread: threading.Thread = None
        
        # Configuration
        self.breakeven_profit_pips = 50.0  # Move to BE after 50 pips profit
        self.trailing_distance_pips = 20.0  # Trail by 20 pips
        
        logger.info("✅ Position Manager initialized")
    
    def start(self, check_interval: int = 60):
        """Start position monitoring"""
        if self.running:
            logger.warning("Position manager already running")
            return
        
        self.running = True
        self.check_interval = check_interval
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"✅ Position manager started (check interval: {check_interval}s)")
    
    def stop(self):
        """Stop position manager"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        logger.info("✅ Position manager stopped")
    
    def register_trade(self, trade_id: str, account_id: str, instrument: str, entry_price: float, side: str):
        """Register a new trade for monitoring"""
        self.trade_entries[trade_id] = {
            'account_id': account_id,
            'instrument': instrument,
            'entry_price': entry_price,
            'side': side,
            'entry_time': datetime.utcnow()
        }
        self.breakeven_moved[trade_id] = False
        logger.debug(f"📝 Registered trade {trade_id} for monitoring")
    
    def _monitor_loop(self):
        """Monitor open positions"""
        logger.info("🔄 Starting position monitoring loop")
        
        while self.running:
            try:
                for account in self.accounts:
                    if not account.get('enabled', False):
                        continue
                    
                    account_id = account.get('id')
                    if not account_id:
                        continue
                    
                    # Get open trades
                    try:
                        open_trades = self.broker.get_open_trades(account_id)
                        
                        # Only fetch prices if we have open trades
                        if not open_trades:
                            continue
                        
                        instruments = list(set(t.get('instrument') for t in open_trades if t.get('instrument')))
                        if not instruments:
                            continue
                        
                        current_prices = self.broker.get_prices(instruments, account_id)
                        
                        for trade in open_trades:
                            trade_id = trade.get('id')
                            instrument = trade.get('instrument')
                            current_price_data = current_prices.get(instrument)
                            
                            if not current_price_data or trade_id not in self.trade_entries:
                                continue
                            
                            entry_info = self.trade_entries[trade_id]
                            entry_price = entry_info['entry_price']
                            side = entry_info['side']
                            
                            # Get current price
                            current_price = current_price_data.bid if side == 'SELL' else current_price_data.ask
                            
                            # Calculate profit in pips
                            if instrument == 'XAU_USD':
                                # Gold: 1 pip = $1
                                if side == 'BUY':
                                    profit_pips = (current_price - entry_price) * 1.0
                                else:
                                    profit_pips = (entry_price - current_price) * 1.0
                            else:
                                # Forex: 0.0001 = 1 pip (or 0.01 for JPY)
                                pip_size = 0.0001 if 'JPY' not in instrument else 0.01
                                if side == 'BUY':
                                    profit_pips = (current_price - entry_price) / pip_size
                                else:
                                    profit_pips = (entry_price - current_price) / pip_size
                            
                            # Check break-even move
                            if not self.breakeven_moved.get(trade_id, False) and profit_pips >= self.breakeven_profit_pips:
                                self.move_to_breakeven(trade_id, account_id, entry_price)
                                self.breakeven_moved[trade_id] = True
                            
                            # Update trailing stop
                            if profit_pips > 0:
                                self.update_trailing_stop(
                                    trade_id,
                                    account_id,
                                    instrument,
                                    entry_price,
                                    current_price,
                                    side,
                                    profit_pips
                                )
                    
                    except Exception as e:
                        logger.debug(f"Error monitoring account {account_id}: {e}")
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in position monitor: {e}", exc_info=True)
                time.sleep(60)
    
    def move_to_breakeven(self, trade_id: str, account_id: str, entry_price: float):
        """Move stop loss to break-even"""
        try:
            self.broker.modify_trade(
                trade_id=trade_id,
                stop_loss=entry_price,
                account_id=account_id
            )
            logger.info(f"✅ Moved trade {trade_id} to break-even @ {entry_price:.5f}")
        except Exception as e:
            logger.error(f"❌ Failed to move to break-even: {e}")
    
    def update_trailing_stop(
        self,
        trade_id: str,
        account_id: str,
        instrument: str,
        entry_price: float,
        current_price: float,
        side: str,
        profit_pips: float
    ):
        """Update trailing stop loss"""
        try:
            # Calculate pip size
            if instrument == 'XAU_USD':
                pip_size = 1.0
            else:
                pip_size = 0.0001 if 'JPY' not in instrument else 0.01
            
            # Calculate new stop loss based on trailing distance
            if side == 'BUY':
                # For long: trail stop below current price
                new_stop = current_price - (self.trailing_distance_pips * pip_size)
                # Don't move stop below entry price
                new_stop = max(new_stop, entry_price)
            else:
                # For short: trail stop above current price
                new_stop = current_price + (self.trailing_distance_pips * pip_size)
                # Don't move stop above entry price
                new_stop = min(new_stop, entry_price)
            
            # Get current stop loss from trade
            # For now, we'll update if we have a better trailing stop
            last_trailing = self.trailing_stops.get(trade_id)
            
            should_update = False
            if side == 'BUY':
                # Update if new stop is higher than last
                should_update = last_trailing is None or new_stop > last_trailing
            else:
                # Update if new stop is lower than last
                should_update = last_trailing is None or new_stop < last_trailing
            
            if should_update:
                self.broker.modify_trade(
                    trade_id=trade_id,
                    stop_loss=new_stop,
                    account_id=account_id
                )
                self.trailing_stops[trade_id] = new_stop
                logger.info(f"✅ Updated trailing stop for {trade_id}: {new_stop:.5f}")
        
        except Exception as e:
            logger.error(f"❌ Failed to update trailing stop: {e}")
    
    def cleanup_trade(self, trade_id: str):
        """Remove trade from tracking when closed"""
        if trade_id in self.trade_entries:
            del self.trade_entries[trade_id]
        if trade_id in self.breakeven_moved:
            del self.breakeven_moved[trade_id]
        if trade_id in self.trailing_stops:
            del self.trailing_stops[trade_id]
