#!/usr/bin/env python3
"""
Telegram Alerts
Send real-time notifications via Telegram bot
"""

import os
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TelegramAlert:
    """Telegram alert message"""
    message: str
    alert_type: str  # 'trade', 'risk', 'daily_summary', 'error'
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class TelegramAlerts:
    """Telegram notification service"""
    
    def __init__(self, token: str = None, chat_id: str = None):
        """Initialize Telegram alerts"""
        self.token = token or os.getenv('TELEGRAM_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.token:
            logger.warning("⚠️ TELEGRAM_TOKEN not configured - alerts disabled")
            self.enabled = False
        elif not self.chat_id:
            logger.warning("⚠️ TELEGRAM_CHAT_ID not configured - alerts disabled")
            self.enabled = False
        else:
            self.enabled = True
            self.api_url = f"https://api.telegram.org/bot{self.token}"
            logger.info(f"✅ Telegram Alerts initialized (Chat ID: {self.chat_id})")
    
    def send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Send message to Telegram"""
        if not self.enabled:
            return False
        
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram message: {e}")
            return False
    
    def send_trade_opened(
        self,
        account_id: str,
        instrument: str,
        side: str,
        units: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        strategy_name: str
    ):
        """Send trade opened alert"""
        side_emoji = "🟢" if side == "BUY" else "🔴"
        message = f"""
{side_emoji} <b>Trade Opened</b>

📊 <b>Instrument:</b> {instrument}
📈 <b>Side:</b> {side}
💰 <b>Units:</b> {abs(units)}
💵 <b>Entry:</b> {entry_price:.5f}
🛑 <b>Stop Loss:</b> {stop_loss:.5f}
🎯 <b>Take Profit:</b> {take_profit:.5f}
📋 <b>Strategy:</b> {strategy_name}
🏦 <b>Account:</b> {account_id[-8:]}
⏰ <b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""
        self.send_message(message)
    
    def send_trade_closed(
        self,
        account_id: str,
        instrument: str,
        side: str,
        units: int,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        strategy_name: str,
        exit_reason: str
    ):
        """Send trade closed alert"""
        pnl_emoji = "✅" if pnl >= 0 else "❌"
        pnl_color = "🟢" if pnl >= 0 else "🔴"
        
        message = f"""
{pnl_emoji} <b>Trade Closed</b>

📊 <b>Instrument:</b> {instrument}
📈 <b>Side:</b> {side}
💰 <b>Units:</b> {abs(units)}
💵 <b>Entry:</b> {entry_price:.5f}
💵 <b>Exit:</b> {exit_price:.5f}
{pnl_color} <b>P&L:</b> ${pnl:.2f} ({pnl_pct:+.2f}%)
📋 <b>Strategy:</b> {strategy_name}
🏦 <b>Account:</b> {account_id[-8:]}
🔖 <b>Exit Reason:</b> {exit_reason}
⏰ <b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""
        self.send_message(message)
    
    def send_circuit_breaker_alert(
        self,
        account_id: str,
        daily_loss_pct: float,
        current_balance: float
    ):
        """Send circuit breaker triggered alert"""
        message = f"""
🔴 <b>CIRCUIT BREAKER TRIGGERED</b>

⚠️ Trading stopped for account {account_id[-8:]}

📉 <b>Daily Loss:</b> {daily_loss_pct:.2f}%
💰 <b>Current Balance:</b> ${current_balance:.2f}

🔒 All trading has been stopped for this account.
Review the system before manually resetting the circuit breaker.
"""
        self.send_message(message)
    
    def send_risk_warning(
        self,
        account_id: str,
        warning_type: str,
        message: str
    ):
        """Send risk warning"""
        warning_message = f"""
⚠️ <b>Risk Warning</b>

🏦 <b>Account:</b> {account_id[-8:]}
📋 <b>Type:</b> {warning_type}

{message}

⏰ <b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""
        self.send_message(warning_message)
    
    def send_daily_summary(
        self,
        account_id: str,
        start_balance: float,
        end_balance: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        win_rate: float
    ):
        """Send end-of-day summary"""
        pnl_emoji = "✅" if daily_pnl >= 0 else "❌"
        
        message = f"""
{pnl_emoji} <b>Daily Summary</b>

🏦 <b>Account:</b> {account_id[-8:]}
📅 <b>Date:</b> {datetime.utcnow().strftime('%Y-%m-%d')}

💰 <b>Balance:</b> ${end_balance:.2f}
📊 <b>Daily P&L:</b> ${daily_pnl:.2f} ({daily_pnl_pct:+.2f}%)
📈 <b>Trades:</b> {total_trades} ({winning_trades}W / {losing_trades}L)
📊 <b>Win Rate:</b> {win_rate:.1f}%

⏰ <b>Time:</b> {datetime.utcnow().strftime('%H:%M UTC')}
"""
        self.send_message(message)
    
    def send_error_alert(
        self,
        error_type: str,
        error_message: str,
        account_id: str = None
    ):
        """Send error alert"""
        account_info = f"\n🏦 <b>Account:</b> {account_id[-8:]}" if account_id else ""
        
        message = f"""
❌ <b>System Error</b>

📋 <b>Type:</b> {error_type}
{account_info}

<code>{error_message}</code>

⏰ <b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""
        self.send_message(message)
    
    def send_morning_briefing(
        self,
        accounts: List[Dict],
        market_status: str
    ):
        """Send morning briefing"""
        message = f"""
🌅 <b>Morning Briefing</b>

📅 <b>Date:</b> {datetime.utcnow().strftime('%Y-%m-%d')}
⏰ <b>Time:</b> {datetime.utcnow().strftime('%H:%M UTC')}
📊 <b>Market Status:</b> {market_status}

<b>Account Status:</b>
"""
        
        for account in accounts:
            account_id = account.get('account_id', '')[-8:]
            balance = account.get('balance', 0)
            open_positions = account.get('open_position_count', 0)
            message += f"\n🏦 {account_id}: ${balance:.2f} | {open_positions} positions"
        
        message += f"\n\n🚀 System ready for trading"
        self.send_message(message)

