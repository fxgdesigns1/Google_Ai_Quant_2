#!/usr/bin/env python3
"""
Unified Trading System & Dashboard Server
Initializes the trading system and starts the dashboard web server
"""

import os
import sys
import logging
import yaml
import threading
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dashboard.app import app, socketio, set_system_components

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import trading system (may fail if dependencies missing)
try:
    from main import initialize_system, load_config
    TRADING_SYSTEM_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Trading system not available: {e}")
    TRADING_SYSTEM_AVAILABLE = False
    def initialize_system(*args, **kwargs):
        raise NotImplementedError("Trading system dependencies not installed")
    def load_config():
        raise NotImplementedError("Trading system dependencies not installed")


def start_background_updates(system_components):
    """Background thread to emit WebSocket updates"""
    from datetime import datetime
    
    def update_loop():
        while True:
            try:
                time.sleep(2)  # Update every 2 seconds
                
                if not system_components:
                    continue
                
                # Emit position updates
                try:
                    broker = system_components.get('broker')
                    config = system_components.get('config')
                    if broker and config:
                        positions = []
                        for account_config in config.get('accounts', []):
                            try:
                                account_positions = broker.get_open_positions(account_config['id'])
                                for instrument, position in account_positions.items():
                                    positions.append({
                                        'account_id': account_config['id'],
                                        'instrument': instrument,
                                        'long_units': position.long_units,
                                        'short_units': position.short_units,
                                        'unrealized_pl': position.unrealized_pl
                                    })
                            except Exception as e:
                                logger.debug(f"Error getting positions for {account_config['id']}: {e}")
                        
                        if positions:
                            socketio.emit('positions_update', {'positions': positions})
                except Exception as e:
                    logger.debug(f"Error in position update: {e}")
                
                # Emit system status
                try:
                    market_data = system_components.get('market_data')
                    socketio.emit('system_status', {
                        'market_data_running': market_data.running if market_data else False,
                        'timestamp': datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logger.debug(f"Error in status update: {e}")
                
            except Exception as e:
                logger.debug(f"Error in background update loop: {e}")
                time.sleep(5)
    
    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()
    return thread


def main():
    """Start unified trading system and dashboard"""
    try:
        logger.info("=" * 60)
        logger.info("🎯 Unified Trading System & Dashboard")
        logger.info("=" * 60)
        
        # Load configuration
        system_components = None
        if not TRADING_SYSTEM_AVAILABLE:
            logger.warning("⚠️ Trading system dependencies not available")
            logger.info("⚠️ Dashboard will run in standalone mode (no trading system)")
        else:
            try:
                config = load_config()
                logger.info("✅ Configuration loaded")
                
                # Initialize trading system
                try:
                    logger.info("🚀 Initializing trading system...")
                    system_components = initialize_system(config)
                    
                    # Start market data feed
                    system_components['market_data'].start()
                    logger.info("✅ Market data feed started")
                    
                    # Start position manager
                    position_check_interval = config.get('system', {}).get('position_check_interval_seconds', 60)
                    system_components['position_manager'].start(check_interval=position_check_interval)
                    logger.info("✅ Position manager started")
                    
                    # Start trade closer (for adaptive learning)
                    if system_components.get('trade_closer'):
                        system_components['trade_closer'].start(check_interval=60)
                        logger.info("✅ Trade closer started")
                    
                    # Start strategy coordinator
                    system_components['strategy_coordinator'].start()
                    logger.info("✅ Strategy coordinator started")
                    
                    # Send morning briefing if Telegram is enabled
                    if system_components.get('telegram_alerts') and system_components['telegram_alerts'].enabled:
                        try:
                            accounts_info = []
                            for account in config.get('accounts', []):
                                if account.get('enabled', False):
                                    try:
                                        account_data = system_components['broker'].get_account(account['id'])
                                        accounts_info.append({
                                            'account_id': account['id'],
                                            'balance': account_data.balance,
                                            'open_position_count': account_data.open_position_count
                                        })
                                    except Exception as e:
                                        logger.debug(f"Could not get account info for {account['id']}: {e}")
                            
                            if accounts_info:
                                system_components['telegram_alerts'].send_morning_briefing(
                                    accounts=accounts_info,
                                    market_status=system_components['risk_manager'].get_session_name()
                                )
                        except Exception as e:
                            logger.debug(f"Could not send morning briefing: {e}")
                    
                    logger.info("✅ Trading system fully initialized")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to initialize trading system: {e}", exc_info=True)
                    logger.info("⚠️ Dashboard will run in standalone mode (no trading system)")
                    system_components = None
            except Exception as e:
                logger.error(f"❌ Failed to load config: {e}")
                logger.info("⚠️ Dashboard will run in standalone mode (no trading system)")
                system_components = None
        
        # Set system components in dashboard app
        set_system_components(system_components)
        
        # Start background WebSocket updates
        if system_components:
            start_background_updates(system_components)
            logger.info("✅ Background WebSocket updates started")
        
        # Get dashboard config
        dashboard_host = os.getenv('DASHBOARD_HOST', '0.0.0.0')
        dashboard_port = int(os.getenv('DASHBOARD_PORT', 5000))
        
        logger.info("=" * 60)
        logger.info(f"✅ Starting dashboard on http://{dashboard_host}:{dashboard_port}")
        logger.info("=" * 60)
        logger.info("Press Ctrl+C to stop")
        
        # Start Flask-SocketIO server (using threading mode)
        socketio.run(
            app,
            host=dashboard_host,
            port=dashboard_port,
            debug=False,
            allow_unsafe_werkzeug=True,
            use_reloader=False
        )
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Shutting down...")
        if system_components:
            try:
                system_components['strategy_coordinator'].stop()
                if system_components.get('trade_closer'):
                    system_components['trade_closer'].stop()
                system_components['position_manager'].stop()
                system_components['market_data'].stop()
                logger.info("✅ Trading system stopped")
            except Exception as e:
                logger.error(f"Error stopping system: {e}")
        logger.info("✅ Dashboard stopped")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
