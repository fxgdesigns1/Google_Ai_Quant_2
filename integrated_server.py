#!/usr/bin/env python3
"""
Integrated Trading System Server
Runs both the trading system and dashboard together with full integration
"""

import os
import sys
import logging
import threading
import signal
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.broker_api import OandaBroker
from core.market_data import MarketDataFeed
from core.risk_manager import RiskManager, RiskLimits
from core.order_executor import OrderExecutor
from monitoring.telegram_alerts import TelegramAlerts
from database.trade_logger import TradeLogger
from orchestrator.position_manager import PositionManager
from orchestrator.strategy_coordinator import StrategyCoordinator
from intelligence.news_aggregator import NewsAggregator
from intelligence.adaptive_learning import AdaptiveLearning
from orchestrator.trade_closer import TradeCloser
from dashboard.app import app, socketio, set_system_components

# Strategy imports
from strategies.gold_momentum import GoldMomentumStrategy
from strategies.gold_scalping import GoldScalpingStrategy
from strategies.gbp_usd_momentum import GbpUsdMomentumStrategy

# Global system reference
system_components = {}
shutdown_event = threading.Event()


def load_config():
    """Load configuration from config.yaml"""
    config_path = project_root / 'config.yaml'
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    logger.info("✅ Configuration loaded")
    return config


def initialize_system(config):
    """Initialize all system components"""
    logger.info("🚀 Initializing trading system...")
    
    # Initialize broker
    api_key = os.getenv('OANDA_API_KEY')
    environment = os.getenv('OANDA_ENVIRONMENT', 'practice')
    
    if not api_key:
        raise ValueError("OANDA_API_KEY not found in environment")
    
    # Get first account ID for broker initialization
    accounts = config.get('accounts', [])
    if not accounts:
        raise ValueError("No accounts configured in config.yaml")
    
    first_account_id = accounts[0]['id']
    broker = OandaBroker(api_key=api_key, account_id=first_account_id, environment=environment)
    
    # Collect all instruments from all accounts
    all_instruments = set()
    for account in accounts:
        if account.get('enabled', False):
            all_instruments.update(account.get('instruments', []))
    
    # Initialize market data feed
    update_interval = config.get('system', {}).get('data_update_interval_seconds', 5)
    market_data = MarketDataFeed(
        broker=broker,
        instruments=list(all_instruments),
        update_interval=update_interval
    )
    
    # Initialize Telegram alerts
    telegram_enabled = config.get('telegram', {}).get('enabled', False)
    telegram_alerts = None
    if telegram_enabled:
        try:
            telegram_alerts = TelegramAlerts()
            if telegram_alerts.enabled:
                logger.info("✅ Telegram alerts initialized")
            else:
                telegram_alerts = None
                logger.warning("⚠️ Telegram alerts disabled (missing token/chat_id)")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Telegram alerts: {e}")
            telegram_alerts = None
    
    # Initialize news aggregator
    news_aggregator = None
    try:
        news_aggregator = NewsAggregator(config)
        if news_aggregator.is_enabled():
            logger.info("✅ News aggregator initialized")
            # Refresh calendar on startup
            news_aggregator.refresh_calendar()
        else:
            logger.warning("⚠️ News aggregator disabled (no API keys)")
            news_aggregator = None
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize news aggregator: {e}")
        news_aggregator = None
    
    # Initialize trade logger
    trade_logger = None
    try:
        trade_logger = TradeLogger()
        logger.info("✅ Trade logger initialized")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize trade logger: {e}")
    
    # Initialize adaptive learning
    adaptive_learning = None
    try:
        adaptive_learning = AdaptiveLearning(trade_logger=trade_logger)
        logger.info("✅ Adaptive learning initialized")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize adaptive learning: {e}")
        adaptive_learning = None
    
    # Initialize risk manager
    global_risk = config.get('global_risk', {})
    risk_limits = RiskLimits(
        max_risk_per_trade=global_risk.get('max_risk_per_trade', 0.02),
        max_portfolio_risk=global_risk.get('max_portfolio_risk', 0.75),
        max_positions=global_risk.get('max_total_positions', 20),
        max_positions_per_instrument=global_risk.get('max_positions_per_instrument', 3),
        max_correlated_pairs=global_risk.get('max_correlated_pairs', 2),
        max_spread_pips=global_risk.get('max_spread_pips', 3.0),
        min_signal_confidence=global_risk.get('min_signal_confidence', 0.7),
        circuit_breaker_loss_pct=global_risk.get('circuit_breaker_loss_pct', 2.0),
        max_exposure_per_instrument_pct=30.0
    )
    risk_manager = RiskManager(limits=risk_limits, telegram_alerts=telegram_alerts, news_aggregator=news_aggregator)
    
    # Initialize position manager
    position_manager = PositionManager(
        broker=broker,
        risk_manager=risk_manager,
        accounts=accounts
    )
    
    # Initialize order executor with all integrations
    order_executor = OrderExecutor(
        broker=broker,
        risk_manager=risk_manager,
        telegram_alerts=telegram_alerts,
        trade_logger=trade_logger,
        position_manager=position_manager,
        adaptive_learning=adaptive_learning
    )
    
    # Load strategies based on config
    strategy_map = {
        'gold_momentum': GoldMomentumStrategy,
        'gold_scalping': GoldScalpingStrategy,
        'gbp_usd_momentum': GbpUsdMomentumStrategy
    }
    
    strategies = []
    for account in accounts:
        if not account.get('enabled', False):
            continue
        
        strategy_name = account.get('strategy')
        if not strategy_name:
            continue
        
        strategy_class = strategy_map.get(strategy_name)
        if not strategy_class:
            logger.warning(f"⚠️ Unknown strategy: {strategy_name}")
            continue
        
        # Create strategy config from account config
        strategy_config = {
            'name': account.get('name', strategy_name),
            'instruments': account.get('instruments', []),
            'enabled': account.get('enabled', False),
            **account.get('strategy_params', {})  # Allow strategy-specific params
        }
        
        try:
            strategy = strategy_class(strategy_config)
            strategies.append(strategy)
            logger.info(f"✅ Loaded strategy: {strategy_name} for account {account.get('name')}")
        except Exception as e:
            logger.error(f"❌ Failed to load strategy {strategy_name}: {e}", exc_info=True)
    
    # Initialize strategy coordinator
    strategy_coordinator = StrategyCoordinator(
        strategies=strategies,
        market_data=market_data,
        order_executor=order_executor,
        risk_manager=risk_manager,
        config=config
    )
    
    # Initialize trade closer (monitors closed trades for adaptive learning)
    trade_closer = None
    if adaptive_learning:
        try:
            trade_closer = TradeCloser(
                broker=broker,
                trade_logger=trade_logger,
                adaptive_learning=adaptive_learning,
                accounts=accounts
            )
            logger.info("✅ Trade closer initialized")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize trade closer: {e}")
            trade_closer = None
    
    logger.info("✅ System initialization complete")
    
    return {
        'broker': broker,
        'market_data': market_data,
        'risk_manager': risk_manager,
        'order_executor': order_executor,
        'position_manager': position_manager,
        'strategy_coordinator': strategy_coordinator,
        'telegram_alerts': telegram_alerts,
        'trade_logger': trade_logger,
        'news_aggregator': news_aggregator,
        'adaptive_learning': adaptive_learning,
        'trade_closer': trade_closer,
        'config': config
    }


def start_trading_system(system):
    """Start all trading system components"""
    logger.info("📈 Starting trading system components...")
    
    # Start market data feed
    system['market_data'].start()
    logger.info("✅ Market data feed started")
    
    # Start position manager
    position_check_interval = system['config'].get('system', {}).get('position_check_interval_seconds', 60)
    system['position_manager'].start(check_interval=position_check_interval)
    logger.info("✅ Position manager started")
    
    # Start trade closer (for adaptive learning)
    if system['trade_closer']:
        system['trade_closer'].start(check_interval=60)
        logger.info("✅ Trade closer started")
    
    # Start strategy coordinator
    system['strategy_coordinator'].start()
    logger.info("✅ Strategy coordinator started")
    
    # Send morning briefing if Telegram is enabled
    if system['telegram_alerts'] and system['telegram_alerts'].enabled:
        try:
            accounts_info = []
            for account in system['config'].get('accounts', []):
                if account.get('enabled', False):
                    try:
                        account_data = system['broker'].get_account(account['id'])
                        accounts_info.append({
                            'account_id': account['id'],
                            'balance': account_data.balance,
                            'open_position_count': account_data.open_position_count
                        })
                    except Exception as e:
                        logger.debug(f"Could not get account info for {account['id']}: {e}")
            
            if accounts_info:
                system['telegram_alerts'].send_morning_briefing(
                    accounts=accounts_info,
                    market_status=system['risk_manager'].get_session_name()
                )
        except Exception as e:
            logger.debug(f"Could not send morning briefing: {e}")


def stop_trading_system(system):
    """Stop all trading system components"""
    logger.info("🛑 Stopping trading system components...")
    
    try:
        if 'strategy_coordinator' in system and system['strategy_coordinator']:
            system['strategy_coordinator'].stop()
        
        if 'trade_closer' in system and system['trade_closer']:
            system['trade_closer'].stop()
        
        if 'position_manager' in system and system['position_manager']:
            system['position_manager'].stop()
        
        if 'market_data' in system and system['market_data']:
            system['market_data'].stop()
        
        logger.info("✅ Trading system stopped")
    except Exception as e:
        logger.error(f"Error stopping trading system: {e}", exc_info=True)


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info("\n🛑 Shutdown signal received...")
    shutdown_event.set()
    stop_trading_system(system_components)
    sys.exit(0)


def main():
    """Main entry point"""
    try:
        logger.info("=" * 60)
        logger.info("🎯 Integrated Trading System & Dashboard")
        logger.info("=" * 60)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Load configuration
        config = load_config()
        
        # Initialize system
        system = initialize_system(config)
        
        # Store system components globally for dashboard access
        global system_components
        system_components = system
        
        # Connect system components to dashboard
        set_system_components(system_components)
        logger.info("✅ Dashboard connected to trading system")
        
        # Start trading system in background thread
        trading_thread = threading.Thread(target=start_trading_system, args=(system,), daemon=True)
        trading_thread.start()
        
        # Get dashboard config
        dashboard_host = config.get('dashboard', {}).get('host', os.getenv('DASHBOARD_HOST', '0.0.0.0'))
        dashboard_port = config.get('dashboard', {}).get('port', int(os.getenv('DASHBOARD_PORT', 5000)))
        
        logger.info("=" * 60)
        logger.info(f"✅ Trading system is running")
        logger.info(f"✅ Dashboard available at: http://{dashboard_host}:{dashboard_port}")
        logger.info("=" * 60)
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        # Start dashboard server (this will block)
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
        stop_trading_system(system_components)
        logger.info("✅ System stopped")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        stop_trading_system(system_components)
        sys.exit(1)


if __name__ == '__main__':
    main()
