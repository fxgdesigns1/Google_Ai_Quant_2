#!/usr/bin/env python3
"""
Dashboard Server Entry Point
Starts the Flask dashboard web server
"""

import os
import sys
import logging
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


def main():
    """Start dashboard server"""
    try:
        logger.info("=" * 60)
        logger.info("📊 Trading System Dashboard")
        logger.info("=" * 60)
        
        # Load system components (optional - dashboard can run standalone)
        # For now, set to None - components will be set if main.py is also running
        set_system_components(None)
        
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
