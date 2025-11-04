#!/usr/bin/env python3
"""
Base Strategy Class
Standard interface for all trading strategies
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.order_executor import TradeSignal

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Base class for all trading strategies"""
    
    def __init__(self, config: Dict):
        """Initialize strategy from config"""
        self.name = config.get('name', 'Unknown Strategy')
        self.instruments = config.get('instruments', [])
        self.timeframe = config.get('timeframe', 'M5')
        self.enabled = config.get('enabled', True)
        self.config = config
        
        logger.info(f"✅ Strategy initialized: {self.name}")
        logger.info(f"   Instruments: {self.instruments}")
        logger.info(f"   Enabled: {self.enabled}")
    
    @abstractmethod
    def analyze(self, market_data: Dict) -> List[TradeSignal]:
        """
        Analyze market data and generate trade signals
        
        Args:
            market_data: Dictionary of instrument -> BrokerPrice or MarketDataFeed
            
        Returns:
            List of TradeSignal objects
        """
        pass
    
    def validate_signal(self, signal: TradeSignal) -> bool:
        """
        Optional: Additional strategy-specific signal validation
        
        Override this in subclasses for strategy-specific checks
        """
        return True
    
    def is_enabled(self) -> bool:
        """Check if strategy is enabled"""
        return self.enabled
    
    def enable(self):
        """Enable the strategy"""
        self.enabled = True
        logger.info(f"✅ Strategy enabled: {self.name}")
    
    def disable(self):
        """Disable the strategy"""
        self.enabled = False
        logger.info(f"⏸️ Strategy disabled: {self.name}")
    
    def get_instruments(self) -> List[str]:
        """Get list of instruments this strategy trades"""
        return self.instruments.copy()
    
    def get_name(self) -> str:
        """Get strategy name"""
        return self.name
