#!/usr/bin/env python3
"""
Adaptive Learning System
Tracks strategy performance and optimizes parameters based on results
"""

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


DEFAULT_PARAMS = {
    "EUR_USD": {"k_atr": 1.25, "ema": 50, "atr": 14, "tp_mult": 1.3, "sl_mult": 0.5},
    "GBP_USD": {"k_atr": 1.25, "ema": 50, "atr": 14, "tp_mult": 1.3, "sl_mult": 0.5},
    "AUD_USD": {"k_atr": 1.25, "ema": 50, "atr": 14, "tp_mult": 1.3, "sl_mult": 0.5},
    "USD_JPY": {"k_atr": 1.00, "ema": 50, "atr": 14, "tp_mult": 1.6, "sl_mult": 0.4},
    "XAU_USD": {"k_atr": 1.50, "ema": 50, "atr": 14, "tp_mult": 1.0, "sl_mult": 0.5},
}


class AdaptiveStore:
    """Thread-safe parameter store for adaptive learning"""
    
    def __init__(self, store_path: str = None):
        """Initialize adaptive store"""
        if store_path is None:
            store_path = Path(__file__).parent.parent / 'data' / 'adaptive_params.json'
        
        self._path = Path(store_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._params = DEFAULT_PARAMS.copy()
        self._load()
        
        logger.info(f"✅ Adaptive Store initialized: {self._path}")
    
    def _load(self):
        """Load parameters from file"""
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text())
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            self._params.setdefault(k, {}).update(v)
                logger.info(f"📂 Loaded adaptive parameters from {self._path}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load adaptive params: {e}, using defaults")
            self._params = DEFAULT_PARAMS.copy()
    
    def _save(self):
        """Save parameters to file"""
        try:
            with self._lock:
                self._path.write_text(json.dumps(self._params, indent=2))
        except Exception as e:
            logger.error(f"❌ Failed to save adaptive params: {e}")
    
    def get(self, instrument: str) -> Dict:
        """Get parameters for an instrument"""
        with self._lock:
            return self._params.get(instrument, DEFAULT_PARAMS.get(instrument, DEFAULT_PARAMS["EUR_USD"])).copy()
    
    def set_param(self, instrument: str, key: str, value: float):
        """Set a parameter for an instrument"""
        with self._lock:
            self._params.setdefault(instrument, {}).update({key: value})
            self._save()
    
    def set_params(self, instrument: str, params: Dict):
        """Set multiple parameters for an instrument"""
        with self._lock:
            self._params.setdefault(instrument, {}).update(params)
            self._save()


class AdaptiveLearning:
    """Adaptive learning system for strategy optimization"""
    
    def __init__(self, trade_logger=None, store_path: str = None):
        """Initialize adaptive learning system"""
        self.trade_logger = trade_logger
        self.store = AdaptiveStore(store_path)
        
        # Performance tracking
        self.instrument_performance: Dict[str, Dict] = {}
        self.strategy_performance: Dict[str, Dict] = {}
        
        # Optimization settings
        self.min_trades_for_optimization = 20  # Minimum trades before optimizing
        self.optimization_window_days = 7  # Look back 7 days
        self.param_adjustment_rate = 0.1  # 10% adjustment per iteration
        
        logger.info("✅ Adaptive Learning System initialized")
    
    def track_trade(self, instrument: str, strategy_name: str, pnl: float, pnl_pct: float):
        """Track a completed trade for learning"""
        if instrument not in self.instrument_performance:
            self.instrument_performance[instrument] = {
                'trades': [],
                'total_pnl': 0.0,
                'win_count': 0,
                'loss_count': 0
            }
        
        perf = self.instrument_performance[instrument]
        perf['trades'].append({
            'strategy': strategy_name,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'timestamp': datetime.utcnow().isoformat()
        })
        perf['total_pnl'] += pnl
        if pnl > 0:
            perf['win_count'] += 1
        else:
            perf['loss_count'] += 1
        
        # Track strategy performance
        if strategy_name not in self.strategy_performance:
            self.strategy_performance[strategy_name] = {
                'trades': [],
                'total_pnl': 0.0,
                'win_count': 0,
                'loss_count': 0
            }
        
        strat_perf = self.strategy_performance[strategy_name]
        strat_perf['trades'].append({
            'instrument': instrument,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'timestamp': datetime.utcnow().isoformat()
        })
        strat_perf['total_pnl'] += pnl
        if pnl > 0:
            strat_perf['win_count'] += 1
        else:
            strat_perf['loss_count'] += 1
    
    def optimize_parameters(self, instrument: str) -> Optional[Dict]:
        """
        Optimize parameters for an instrument based on recent performance
        
        Returns:
            Optimized parameters dict or None if not enough data
        """
        if instrument not in self.instrument_performance:
            return None
        
        perf = self.instrument_performance[instrument]
        recent_trades = perf['trades']
        
        # Filter to recent trades (within optimization window)
        cutoff = datetime.utcnow() - timedelta(days=self.optimization_window_days)
        recent_trades = [
            t for t in recent_trades 
            if datetime.fromisoformat(t['timestamp']) >= cutoff
        ]
        
        if len(recent_trades) < self.min_trades_for_optimization:
            return None
        
        # Calculate performance metrics
        total_trades = len(recent_trades)
        win_count = sum(1 for t in recent_trades if t['pnl'] > 0)
        win_rate = win_count / total_trades if total_trades > 0 else 0
        avg_pnl = sum(t['pnl'] for t in recent_trades) / total_trades
        
        # Get current parameters
        current_params = self.store.get(instrument)
        
        # Adjust parameters based on performance
        optimized_params = current_params.copy()
        
        # If win rate is low, tighten stops (reduce SL multiplier)
        if win_rate < 0.4:
            optimized_params['sl_mult'] = max(0.3, current_params.get('sl_mult', 0.5) * (1 - self.param_adjustment_rate))
            logger.info(f"📉 {instrument}: Low win rate ({win_rate:.1%}), tightening stops")
        
        # If win rate is high, can widen stops slightly
        elif win_rate > 0.6:
            optimized_params['sl_mult'] = min(0.7, current_params.get('sl_mult', 0.5) * (1 + self.param_adjustment_rate))
            logger.info(f"📈 {instrument}: High win rate ({win_rate:.1%}), widening stops")
        
        # Adjust TP multiplier based on average P&L
        if avg_pnl > 0:
            optimized_params['tp_mult'] = min(2.0, current_params.get('tp_mult', 1.3) * (1 + self.param_adjustment_rate))
        else:
            optimized_params['tp_mult'] = max(1.0, current_params.get('tp_mult', 1.3) * (1 - self.param_adjustment_rate))
        
        # Adjust ATR multiplier based on volatility
        if abs(avg_pnl) > abs(sum(t['pnl'] for t in recent_trades[-10:]) / min(10, len(recent_trades))):
            # High volatility
            optimized_params['k_atr'] = min(2.0, current_params.get('k_atr', 1.25) * (1 + self.param_adjustment_rate))
        else:
            # Low volatility
            optimized_params['k_atr'] = max(1.0, current_params.get('k_atr', 1.25) * (1 - self.param_adjustment_rate))
        
        # Save optimized parameters
        self.store.set_params(instrument, optimized_params)
        
        logger.info(f"✅ Optimized parameters for {instrument}:")
        logger.info(f"   Win rate: {win_rate:.1%} ({win_count}/{total_trades})")
        logger.info(f"   Avg P&L: ${avg_pnl:.2f}")
        logger.info(f"   New params: SL={optimized_params['sl_mult']:.2f}, TP={optimized_params['tp_mult']:.2f}, ATR={optimized_params['k_atr']:.2f}")
        
        return optimized_params
    
    def get_performance_summary(self, instrument: str = None, strategy_name: str = None) -> Dict:
        """Get performance summary for instrument or strategy"""
        if instrument:
            perf = self.instrument_performance.get(instrument, {})
            total_trades = len(perf.get('trades', []))
            win_rate = perf.get('win_count', 0) / total_trades if total_trades > 0 else 0
            return {
                'instrument': instrument,
                'total_trades': total_trades,
                'win_rate': win_rate,
                'total_pnl': perf.get('total_pnl', 0.0),
                'win_count': perf.get('win_count', 0),
                'loss_count': perf.get('loss_count', 0)
            }
        
        if strategy_name:
            perf = self.strategy_performance.get(strategy_name, {})
            total_trades = len(perf.get('trades', []))
            win_rate = perf.get('win_count', 0) / total_trades if total_trades > 0 else 0
            return {
                'strategy': strategy_name,
                'total_trades': total_trades,
                'win_rate': win_rate,
                'total_pnl': perf.get('total_pnl', 0.0),
                'win_count': perf.get('win_count', 0),
                'loss_count': perf.get('loss_count', 0)
            }
        
        return {}
    
    def should_optimize(self, instrument: str) -> bool:
        """Check if there's enough data to optimize parameters"""
        if instrument not in self.instrument_performance:
            return False
        
        perf = self.instrument_performance[instrument]
        recent_trades = perf['trades']
        
        # Filter to recent trades
        cutoff = datetime.utcnow() - timedelta(days=self.optimization_window_days)
        recent_trades = [
            t for t in recent_trades 
            if datetime.fromisoformat(t['timestamp']) >= cutoff
        ]
        
        return len(recent_trades) >= self.min_trades_for_optimization

