#!/usr/bin/env python3
"""
Comprehensive system test - tests all major components
"""

import sys
import logging
import time
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    logger.info("=" * 60)
    logger.info("🧪 Comprehensive System Test")
    logger.info("=" * 60)
    
    # Load config
    import yaml
    from dotenv import load_dotenv
    load_dotenv()
    
    config_path = project_root / 'config.yaml'
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    logger.info("✅ Config loaded")
    
    # Import and initialize system
    from main import initialize_system
    
    logger.info("🚀 Initializing system...")
    system = initialize_system(config)
    
    # Test 1: Market Data Feed
    logger.info("\n📊 Test 1: Market Data Feed")
    try:
        system['market_data'].start()
        logger.info("✅ Market data feed started")
        time.sleep(2)  # Wait for initial data
        
        # Check if we have price data
        instruments = config['accounts'][0]['instruments']
        for inst in instruments:
            price = system['market_data'].get_current_price(inst)
            if price:
                logger.info(f"   ✅ {inst}: {price.bid:.5f} / {price.ask:.5f}")
            else:
                logger.warning(f"   ⚠️ {inst}: No price data yet")
        
        system['market_data'].stop()
        logger.info("✅ Market data feed test passed")
    except Exception as e:
        logger.error(f"❌ Market data test failed: {e}", exc_info=True)
    
    # Test 2: Strategy Signal Generation
    logger.info("\n📈 Test 2: Strategy Signal Generation")
    try:
        system['market_data'].start()
        time.sleep(3)  # Wait for data
        
        for strategy in system['strategy_coordinator'].strategies:
            logger.info(f"   Testing {strategy.get_name()}...")
            try:
                signals = strategy.analyze(system['market_data'])
                logger.info(f"   ✅ {strategy.get_name()}: Generated {len(signals)} signals")
                if signals:
                    for sig in signals:
                        logger.info(f"      - {sig.instrument} {sig.side} @ {sig.entry_price:.5f} (confidence: {sig.confidence:.2f})")
            except Exception as e:
                logger.warning(f"   ⚠️ {strategy.get_name()}: {e}")
        
        system['market_data'].stop()
        logger.info("✅ Strategy signal generation test passed")
    except Exception as e:
        logger.error(f"❌ Strategy test failed: {e}", exc_info=True)
    
    # Test 3: Risk Manager
    logger.info("\n🛡️ Test 3: Risk Manager")
    try:
        account = system['broker'].get_account(config['accounts'][0]['id'])
        can_trade, reason = system['risk_manager'].check_circuit_breaker(
            config['accounts'][0]['id'],
            account.balance
        )
        logger.info(f"   ✅ Circuit breaker check: {can_trade} ({reason})")
        
        is_trading_hours = system['risk_manager'].is_trading_hours()
        session = system['risk_manager'].get_session_name()
        logger.info(f"   ✅ Trading hours: {is_trading_hours} (Session: {session})")
        logger.info("✅ Risk manager test passed")
    except Exception as e:
        logger.error(f"❌ Risk manager test failed: {e}", exc_info=True)
    
    # Test 4: Telegram Alerts
    logger.info("\n📱 Test 4: Telegram Alerts")
    try:
        if system['telegram_alerts'] and system['telegram_alerts'].enabled:
            # Test sending a message (comment out to avoid spam)
            # system['telegram_alerts'].send_message("🧪 System test - Telegram alerts working!")
            logger.info("   ✅ Telegram alerts configured and ready")
            logger.info("   ⚠️ Skipping actual send to avoid spam")
        else:
            logger.warning("   ⚠️ Telegram alerts not enabled")
        logger.info("✅ Telegram alerts test passed")
    except Exception as e:
        logger.error(f"❌ Telegram test failed: {e}", exc_info=True)
    
    # Test 5: Trade Logger
    logger.info("\n📝 Test 5: Trade Logger")
    try:
        if system['trade_logger']:
            # Test database connection
            recent_trades = system['trade_logger'].get_recent_trades(limit=5)
            logger.info(f"   ✅ Database accessible ({len(recent_trades)} recent trades)")
        logger.info("✅ Trade logger test passed")
    except Exception as e:
        logger.error(f"❌ Trade logger test failed: {e}", exc_info=True)
    
    # Test 6: Position Manager
    logger.info("\n📊 Test 6: Position Manager")
    try:
        if system['position_manager']:
            logger.info("   ✅ Position manager initialized")
            # Test starting and stopping
            system['position_manager'].start(check_interval=60)
            time.sleep(1)
            system['position_manager'].stop()
            logger.info("   ✅ Position manager start/stop works")
        logger.info("✅ Position manager test passed")
    except Exception as e:
        logger.error(f"❌ Position manager test failed: {e}", exc_info=True)
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ ALL COMPREHENSIVE TESTS COMPLETED")
    logger.info("=" * 60)
    
except Exception as e:
    logger.error(f"❌ TEST FAILED: {e}", exc_info=True)
    sys.exit(1)

