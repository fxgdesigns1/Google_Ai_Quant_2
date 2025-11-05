#!/usr/bin/env python3
"""
Dashboard Server Entry Point
Starts the Flask dashboard web server with integrated trading system
"""

import os
import sys
import logging
import threading
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from flask import Flask
from dashboard.app import app, socketio, set_system_components

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def initialize_system():
    """Initialize the trading system components"""
    try:
        logger.info("🚀 Initializing trading system components...")
        
        # Import after path setup
        import yaml
        from dotenv import load_dotenv
        
        load_dotenv()
        
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
        from strategies.gold_momentum import GoldMomentumStrategy
        from strategies.gold_scalping import GoldScalpingStrategy
        from strategies.gbp_usd_momentum import GbpUsdMomentumStrategy
        
        # Load config
        config_path = project_root / 'config.yaml'
        if not config_path.exists():
            logger.warning("⚠️ Config file not found, dashboard will run in limited mode")
            return None
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Initialize broker
        api_key = os.getenv('OANDA_API_KEY')
        environment = os.getenv('OANDA_ENVIRONMENT', 'practice')
        
        if not api_key:
            logger.warning("⚠️ OANDA_API_KEY not found, dashboard will run in limited mode")
            return {'config': config}
        
        accounts = config.get('accounts', [])
        if not accounts:
            logger.warning("⚠️ No accounts configured")
            return {'config': config}
        
        try:
            first_account_id = accounts[0]['id']
            broker = OandaBroker(api_key=api_key, account_id=first_account_id, environment=environment)
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize broker: {e}, dashboard will run in limited mode")
            return {'config': config}
        
        # Collect instruments
        all_instruments = set()
        for account in accounts:
            if account.get('enabled', False):
                all_instruments.update(account.get('instruments', []))
        
        # Initialize market data
        update_interval = config.get('system', {}).get('data_update_interval_seconds', 5)
        market_data = MarketDataFeed(
            broker=broker,
            instruments=list(all_instruments),
            update_interval=update_interval
        )
        
        # Initialize Telegram
        telegram_alerts = None
        if config.get('telegram', {}).get('enabled', False):
            try:
                telegram_alerts = TelegramAlerts()
                if not telegram_alerts.enabled:
                    telegram_alerts = None
            except Exception as e:
                logger.debug(f"Telegram alerts not available: {e}")
        
        # Initialize news aggregator
        news_aggregator = None
        try:
            news_aggregator = NewsAggregator(config)
            if not news_aggregator.is_enabled():
                news_aggregator = None
            else:
                news_aggregator.refresh_calendar()
        except Exception as e:
            logger.debug(f"News aggregator not available: {e}")
        
        # Initialize trade logger
        trade_logger = None
        try:
            trade_logger = TradeLogger()
        except Exception as e:
            logger.debug(f"Trade logger not available: {e}")
        
        # Initialize adaptive learning
        adaptive_learning = None
        if trade_logger:
            try:
                adaptive_learning = AdaptiveLearning(trade_logger=trade_logger)
            except Exception as e:
                logger.debug(f"Adaptive learning not available: {e}")
        
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
        
        # Initialize order executor
        order_executor = OrderExecutor(
            broker=broker,
            risk_manager=risk_manager,
            telegram_alerts=telegram_alerts,
            trade_logger=trade_logger,
            position_manager=position_manager,
            adaptive_learning=adaptive_learning
        )
        
        # Load strategies
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
                continue
            
            strategy_config = {
                'name': account.get('name', strategy_name),
                'instruments': account.get('instruments', []),
                'enabled': account.get('enabled', False),
                **account.get('strategy_params', {})
            }
            
            try:
                strategy = strategy_class(strategy_config)
                strategies.append(strategy)
            except Exception as e:
                logger.debug(f"Failed to load strategy {strategy_name}: {e}")
        
        # Initialize strategy coordinator
        strategy_coordinator = StrategyCoordinator(
            strategies=strategies,
            market_data=market_data,
            order_executor=order_executor,
            risk_manager=risk_manager,
            config=config
        )
        
        # Initialize trade closer
        trade_closer = None
        if adaptive_learning and trade_logger:
            try:
                trade_closer = TradeCloser(
                    broker=broker,
                    trade_logger=trade_logger,
                    adaptive_learning=adaptive_learning,
                    accounts=accounts
                )
            except Exception as e:
                logger.debug(f"Trade closer not available: {e}")
        
        # Start system components
        market_data.start()
        position_check_interval = config.get('system', {}).get('position_check_interval_seconds', 60)
        position_manager.start(check_interval=position_check_interval)
        
        if trade_closer:
            trade_closer.start(check_interval=60)
        
        strategy_coordinator.start()
        
        logger.info("✅ Trading system components initialized and started")
        
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
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize system: {e}", exc_info=True)
        return None


def main():
    """Start dashboard server"""
    try:
        logger.info("=" * 60)
        logger.info("📊 Trading System Dashboard")
        logger.info("=" * 60)
        
        # Initialize system components
        system_components = initialize_system()
        set_system_components(system_components)
        
        if system_components:
            logger.info("✅ Trading system integrated with dashboard")
        else:
            logger.warning("⚠️ Dashboard running in limited mode (no trading system)")
        
        # Get dashboard config
        dashboard_host = os.getenv('DASHBOARD_HOST', '0.0.0.0')
        dashboard_port = int(os.getenv('DASHBOARD_PORT', 5000))
        
        logger.info(f"✅ Starting dashboard on http://{dashboard_host}:{dashboard_port}")
        logger.info("=" * 60)
        
        # Start Flask-SocketIO server (using threading mode)
        socketio.run(
            app,
            host=dashboard_host,
            port=dashboard_port,
            debug=False,
            allow_unsafe_werkzeug=True,
            use_reloader=False
        )
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
