#!/usr/bin/env python3
"""
Trade Logger
SQLite database for logging all trades, signals, and account snapshots
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import asdict

logger = logging.getLogger(__name__)


class TradeLogger:
    """SQLite trade logger"""
    
    def __init__(self, db_path: str = None):
        """Initialize trade logger"""
        if db_path is None:
            db_path = Path(__file__).parent.parent / 'data' / 'trades.db'
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        logger.info(f"✅ Trade Logger initialized: {self.db_path}")
    
    def _init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE,
                account_id TEXT,
                instrument TEXT,
                side TEXT,
                units INTEGER,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                exit_price REAL,
                pnl REAL,
                pnl_pct REAL,
                strategy_name TEXT,
                entry_time TIMESTAMP,
                exit_time TIMESTAMP,
                duration_minutes INTEGER,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Signals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT UNIQUE,
                instrument TEXT,
                side TEXT,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                confidence REAL,
                strategy_name TEXT,
                status TEXT,
                reason TEXT,
                timestamp TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Account snapshots table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT,
                balance REAL,
                unrealized_pl REAL,
                realized_pl REAL,
                margin_used REAL,
                margin_available REAL,
                open_trade_count INTEGER,
                open_position_count INTEGER,
                timestamp TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades(instrument)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(entry_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_time ON signals(timestamp)')
        
        conn.commit()
        conn.close()
    
    def log_signal(self, signal, status: str = 'GENERATED', reason: str = None):
        """Log a trade signal"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        signal_id = f"{signal.strategy_name}_{signal.instrument}_{int(signal.timestamp.timestamp())}"
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO signals 
                (signal_id, instrument, side, entry_price, stop_loss, take_profit,
                 confidence, strategy_name, status, reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                signal_id,
                signal.instrument,
                signal.side,
                signal.entry_price,
                signal.stop_loss,
                signal.take_profit,
                signal.confidence,
                signal.strategy_name,
                status,
                reason,
                signal.timestamp
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Error logging signal: {e}")
        finally:
            conn.close()
    
    def log_trade(self, trade_data: Dict):
        """Log a trade"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO trades 
                (trade_id, account_id, instrument, side, units, entry_price,
                 stop_loss, take_profit, exit_price, pnl, pnl_pct, strategy_name,
                 entry_time, exit_time, duration_minutes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_data.get('trade_id'),
                trade_data.get('account_id'),
                trade_data.get('instrument'),
                trade_data.get('side'),
                trade_data.get('units'),
                trade_data.get('entry_price'),
                trade_data.get('stop_loss'),
                trade_data.get('take_profit'),
                trade_data.get('exit_price'),
                trade_data.get('pnl'),
                trade_data.get('pnl_pct'),
                trade_data.get('strategy_name'),
                trade_data.get('entry_time'),
                trade_data.get('exit_time'),
                trade_data.get('duration_minutes'),
                trade_data.get('status', 'OPEN')
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Error logging trade: {e}")
        finally:
            conn.close()
    
    def log_account_snapshot(self, account_data: Dict):
        """Log account snapshot"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO account_snapshots
                (account_id, balance, unrealized_pl, realized_pl, margin_used,
                 margin_available, open_trade_count, open_position_count, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                account_data.get('account_id'),
                account_data.get('balance'),
                account_data.get('unrealized_pl'),
                account_data.get('realized_pl'),
                account_data.get('margin_used'),
                account_data.get('margin_available'),
                account_data.get('open_trade_count'),
                account_data.get('open_position_count'),
                datetime.utcnow()
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Error logging account snapshot: {e}")
        finally:
            conn.close()
    
    def get_recent_trades(self, limit: int = 100, account_id: str = None) -> List[Dict]:
        """Get recent trades"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if account_id:
            cursor.execute('''
                SELECT * FROM trades 
                WHERE account_id = ?
                ORDER BY entry_time DESC 
                LIMIT ?
            ''', (account_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM trades 
                ORDER BY entry_time DESC 
                LIMIT ?
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_strategy_performance(self, strategy_name: str) -> Dict:
        """Get performance metrics for a strategy"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) as gross_profit,
                SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END) as gross_loss
            FROM trades
            WHERE strategy_name = ? AND status = 'CLOSED'
        ''', (strategy_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0] > 0:
            total_trades, winning, losing, total_pnl, avg_pnl, gross_profit, gross_loss = row
            win_rate = (winning / total_trades) * 100 if total_trades > 0 else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            return {
                'total_trades': total_trades,
                'winning_trades': winning,
                'losing_trades': losing,
                'win_rate': win_rate,
                'total_pnl': total_pnl or 0,
                'avg_pnl': avg_pnl or 0,
                'profit_factor': profit_factor,
                'gross_profit': gross_profit or 0,
                'gross_loss': gross_loss or 0
            }
        
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'profit_factor': 0,
            'gross_profit': 0,
            'gross_loss': 0
        }
