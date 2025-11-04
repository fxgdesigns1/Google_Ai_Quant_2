#!/usr/bin/env python3
"""
Quick system test - validates initialization without running full loop
"""

import sys
import logging
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
    logger.info("🧪 Testing System Initialization")
    logger.info("=" * 60)
    
    # Load config
    import yaml
    from dotenv import load_dotenv
    load_dotenv()
    
    config_path = project_root / 'config.yaml'
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    logger.info("✅ Config loaded")
    
    # Import and test main initialization function
    from main import initialize_system
    
    logger.info("🚀 Initializing system components...")
    system = initialize_system(config)
    
    logger.info("✅ System initialization successful!")
    logger.info(f"   - Broker: {'✅' if system['broker'] else '❌'}")
    logger.info(f"   - Market Data: {'✅' if system['market_data'] else '❌'}")
    logger.info(f"   - Risk Manager: {'✅' if system['risk_manager'] else '❌'}")
    logger.info(f"   - Order Executor: {'✅' if system['order_executor'] else '❌'}")
    logger.info(f"   - Position Manager: {'✅' if system['position_manager'] else '❌'}")
    logger.info(f"   - Strategy Coordinator: {'✅' if system['strategy_coordinator'] else '❌'}")
    logger.info(f"   - Telegram Alerts: {'✅' if system['telegram_alerts'] and system['telegram_alerts'].enabled else '⚠️'}")
    logger.info(f"   - Trade Logger: {'✅' if system['trade_logger'] else '❌'}")
    
    # Test strategy loading
    strategies_loaded = len(system['strategy_coordinator'].strategies)
    logger.info(f"   - Strategies Loaded: {strategies_loaded}")
    
    logger.info("=" * 60)
    logger.info("✅ ALL TESTS PASSED - System ready!")
    logger.info("=" * 60)
    
except Exception as e:
    logger.error(f"❌ TEST FAILED: {e}", exc_info=True)
    sys.exit(1)

