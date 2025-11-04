#!/usr/bin/env python3
"""
Backtesting Engine
Historical backtesting for strategy validation
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.broker_api import OandaBroker
from core.order_executor import TradeSignal
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """Backtest trade result"""
    entry_time: datetime
    exit_time: datetime
    instrument: str
    side: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    units: int
    pnl: float
    pnl_pct: float
    duration_minutes: int
    exit_reason: str  # 'SL', 'TP', 'TIME', 'MANUAL'


@dataclass
class BacktestResult:
    """Backtest results"""
    strategy_name: str
    instrument: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    total_pnl: float
    total_pnl_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trades: List[BacktestTrade]


class BacktestEngine:
    """Historical backtesting engine"""
    
    def __init__(self, broker: OandaBroker):
        """Initialize backtesting engine"""
        self.broker = broker
        logger.info("✅ Backtest Engine initialized")
    
    def fetch_historical_data(
        self,
        instrument: str,
        start_date: datetime,
        end_date: datetime,
        granularity: str = 'M5'
    ) -> List[Dict]:
        """
        Fetch historical candle data from OANDA
        
        Args:
            instrument: Trading instrument (e.g., 'XAU_USD')
            start_date: Start date for historical data
            end_date: End date for historical data
            granularity: Timeframe (M1, M5, M15, H1, etc.)
        
        Returns:
            List of candle dictionaries with 'time', 'open', 'high', 'low', 'close', 'volume'
        """
        try:
            from oandapyV20.endpoints import instruments
            
            # Convert dates to RFC3339 format
            start_str = start_date.strftime('%Y-%m-%dT%H:%M:%S.000000000Z')
            end_str = end_date.strftime('%Y-%m-%dT%H:%M:%S.000000000Z')
            
            # OANDA API params
            params = {
                'from': start_str,
                'to': end_str,
                'granularity': granularity,
                'price': 'M'  # Mid prices
            }
            
            # Fetch data (OANDA has 5000 candle limit per request)
            all_candles = []
            current_start = start_date
            
            while current_start < end_date:
                current_end = min(current_start + timedelta(days=30), end_date)
                
                params['from'] = current_start.strftime('%Y-%m-%dT%H:%M:%S.000000000Z')
                params['to'] = current_end.strftime('%Y-%m-%dT%H:%M:%S.000000000Z')
                
                r = instruments.InstrumentsCandles(instrument=instrument, params=params)
                response = self.broker.api.request(r)
                
                candles = response.get('candles', [])
                for candle in candles:
                    if candle.get('complete', False):
                        mid = candle.get('mid', {})
                        all_candles.append({
                            'time': datetime.fromisoformat(candle['time'].replace('Z', '+00:00')),
                            'open': float(mid.get('o', 0)),
                            'high': float(mid.get('h', 0)),
                            'low': float(mid.get('l', 0)),
                            'close': float(mid.get('c', 0)),
                            'volume': int(candle.get('volume', 0))
                        })
                
                current_start = current_end
                logger.info(f"📊 Fetched {len(candles)} candles for {instrument} ({current_start.date()} to {current_end.date()})")
            
            logger.info(f"✅ Fetched {len(all_candles)} total candles for {instrument}")
            return all_candles
            
        except Exception as e:
            logger.error(f"❌ Error fetching historical data: {e}", exc_info=True)
            return []
    
    def simulate_market_data(self, candles: List[Dict], current_index: int) -> Dict:
        """Simulate market data feed from historical candles"""
        if current_index >= len(candles):
            return None
        
        candle = candles[current_index]
        
        # Create a simple market data structure
        # In real system, this would be MarketDataFeed
        return {
            'candles': candles[:current_index + 1],
            'current_price': candle['close'],
            'bid': candle['close'] * 0.9999,  # Approximate spread
            'ask': candle['close'] * 1.0001,
            'time': candle['time']
        }
    
    def run_backtest(
        self,
        strategy: BaseStrategy,
        instrument: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float = 10000.0,
        granularity: str = 'M5',
        risk_per_trade_pct: float = 0.01
    ) -> BacktestResult:
        """
        Run backtest on historical data
        
        Args:
            strategy: Strategy instance to test
            instrument: Instrument to backtest
            start_date: Start date
            end_date: End date
            initial_balance: Starting balance
            granularity: Timeframe
            risk_per_trade_pct: Risk per trade percentage
        
        Returns:
            BacktestResult with all metrics
        """
        logger.info(f"🚀 Starting backtest: {strategy.name} on {instrument}")
        logger.info(f"   Period: {start_date.date()} to {end_date.date()}")
        logger.info(f"   Initial balance: ${initial_balance:.2f}")
        
        # Fetch historical data
        candles = self.fetch_historical_data(instrument, start_date, end_date, granularity)
        if len(candles) < 100:
            logger.error(f"❌ Insufficient historical data: {len(candles)} candles")
            return self._empty_result(strategy.name, instrument, start_date, end_date, initial_balance)
        
        # Simulate trading
        balance = initial_balance
        open_trades: List[Dict] = []
        closed_trades: List[BacktestTrade] = []
        equity_curve = [initial_balance]
        peak_balance = initial_balance
        max_drawdown = 0.0
        
        # Create a simple market data simulator
        class MarketDataSimulator:
            def __init__(self, candles):
                self.candles = candles
                self.current_index = 0
            
            def get_price_history(self, inst, period):
                if inst != instrument:
                    return []
                start_idx = max(0, self.current_index - period + 1)
                return [c['close'] for c in self.candles[start_idx:self.current_index + 1]]
            
            def get_close_prices(self, inst, period):
                return self.get_price_history(inst, period)
            
            def get_current_price(self, inst):
                if inst != instrument or self.current_index >= len(self.candles):
                    return None
                candle = self.candles[self.current_index]
                from core.broker_api import BrokerPrice
                return BrokerPrice(
                    instrument=inst,
                    bid=candle['close'] * 0.9999,
                    ask=candle['close'] * 1.0001,
                    spread=candle['close'] * 0.0002,
                    timestamp=candle['time'],
                    time=candle['time'].isoformat()
                )
            
            def calculate_atr(self, inst, period=14):
                if inst != instrument or self.current_index < period:
                    return None
                
                # Calculate ATR from recent candles
                recent = self.candles[max(0, self.current_index - period + 1):self.current_index + 1]
                if len(recent) < 2:
                    return None
                
                tr_values = []
                for i in range(1, len(recent)):
                    high_low = recent[i]['high'] - recent[i]['low']
                    high_close = abs(recent[i]['high'] - recent[i-1]['close'])
                    low_close = abs(recent[i]['low'] - recent[i-1]['close'])
                    tr = max(high_low, high_close, low_close)
                    tr_values.append(tr)
                
                return sum(tr_values) / len(tr_values) if tr_values else None
        
        market_data = MarketDataSimulator(candles)
        
        # Run through historical data
        for i in range(100, len(candles)):  # Start after 100 candles for indicators
            market_data.current_index = i
            candle = candles[i]
            current_time = candle['time']
            current_price = candle['close']
            
            # Check for exit conditions on open trades
            trades_to_close = []
            for trade in open_trades:
                exit_reason = None
                exit_price = None
                
                # Check stop loss
                if trade['side'] == 'BUY' and candle['low'] <= trade['stop_loss']:
                    exit_reason = 'SL'
                    exit_price = trade['stop_loss']
                elif trade['side'] == 'SELL' and candle['high'] >= trade['stop_loss']:
                    exit_reason = 'SL'
                    exit_price = trade['stop_loss']
                
                # Check take profit
                if not exit_reason:
                    if trade['side'] == 'BUY' and candle['high'] >= trade['take_profit']:
                        exit_reason = 'TP'
                        exit_price = trade['take_profit']
                    elif trade['side'] == 'SELL' and candle['low'] <= trade['take_profit']:
                        exit_reason = 'TP'
                        exit_price = trade['take_profit']
                
                # Time-based exit (close after 24 hours)
                if not exit_reason:
                    hours_open = (current_time - trade['entry_time']).total_seconds() / 3600
                    if hours_open >= 24:
                        exit_reason = 'TIME'
                        exit_price = current_price
                
                if exit_reason:
                    # Calculate P&L
                    if trade['side'] == 'BUY':
                        pnl = (exit_price - trade['entry_price']) * trade['units']
                    else:
                        pnl = (trade['entry_price'] - exit_price) * trade['units']
                    
                    pnl_pct = (pnl / balance) * 100
                    balance += pnl
                    
                    duration_minutes = int((current_time - trade['entry_time']).total_seconds() / 60)
                    
                    closed_trade = BacktestTrade(
                        entry_time=trade['entry_time'],
                        exit_time=current_time,
                        instrument=instrument,
                        side=trade['side'],
                        entry_price=trade['entry_price'],
                        exit_price=exit_price,
                        stop_loss=trade['stop_loss'],
                        take_profit=trade['take_profit'],
                        units=trade['units'],
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        duration_minutes=duration_minutes,
                        exit_reason=exit_reason
                    )
                    closed_trades.append(closed_trade)
                    trades_to_close.append(trade)
            
            # Remove closed trades
            for trade in trades_to_close:
                open_trades.remove(trade)
            
            # Generate new signals
            try:
                signals = strategy.analyze(market_data)
                for signal in signals:
                    if signal.instrument == instrument and len(open_trades) < 3:
                        # Calculate position size
                        stop_distance = abs(signal.entry_price - signal.stop_loss)
                        if stop_distance == 0:
                            continue
                        
                        risk_amount = balance * risk_per_trade_pct
                        
                        # Simplified position sizing
                        if instrument == 'XAU_USD':
                            pip_value = 10.0
                            units = int((risk_amount / stop_distance) / pip_value)
                        else:
                            pip_size = 0.0001 if 'JPY' not in instrument else 0.01
                            pip_distance = stop_distance / pip_size
                            units = int((risk_amount / pip_distance) / 10.0 * 10000)
                        
                        units = max(1, units)
                        if signal.side == 'SELL':
                            units = -units
                        
                        # Open trade
                        open_trades.append({
                            'entry_time': current_time,
                            'entry_price': signal.entry_price,
                            'stop_loss': signal.stop_loss,
                            'take_profit': signal.take_profit,
                            'side': signal.side,
                            'units': abs(units),
                            'signal': signal
                        })
            except Exception as e:
                logger.debug(f"Error generating signals: {e}")
            
            # Update equity curve and drawdown
            equity_curve.append(balance)
            if balance > peak_balance:
                peak_balance = balance
            drawdown = (peak_balance - balance) / peak_balance * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Close any remaining open trades at end
        final_price = candles[-1]['close']
        for trade in open_trades:
            pnl = (final_price - trade['entry_price']) * trade['units'] if trade['side'] == 'BUY' else (trade['entry_price'] - final_price) * trade['units']
            balance += pnl
            duration_minutes = int((candles[-1]['time'] - trade['entry_time']).total_seconds() / 60)
            
            closed_trade = BacktestTrade(
                entry_time=trade['entry_time'],
                exit_time=candles[-1]['time'],
                instrument=instrument,
                side=trade['side'],
                entry_price=trade['entry_price'],
                exit_price=final_price,
                stop_loss=trade['stop_loss'],
                take_profit=trade['take_profit'],
                units=trade['units'],
                pnl=pnl,
                pnl_pct=(pnl / initial_balance) * 100,
                duration_minutes=duration_minutes,
                exit_reason='MANUAL'
            )
            closed_trades.append(closed_trade)
        
        # Calculate metrics
        return self._calculate_results(
            strategy_name=strategy.name,
            instrument=instrument,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            final_balance=balance,
            trades=closed_trades,
            max_drawdown=max_drawdown,
            equity_curve=equity_curve
        )
    
    def _calculate_results(
        self,
        strategy_name: str,
        instrument: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float,
        final_balance: float,
        trades: List[BacktestTrade],
        max_drawdown: float,
        equity_curve: List[float]
    ) -> BacktestResult:
        """Calculate backtest metrics"""
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl < 0]
        
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = abs(sum(t.pnl for t in losing_trades) / len(losing_trades)) if losing_trades else 0
        
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        total_pnl = final_balance - initial_balance
        total_pnl_pct = (total_pnl / initial_balance) * 100
        
        # Calculate Sharpe ratio (simplified)
        if len(equity_curve) > 1:
            returns = [(equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1] for i in range(1, len(equity_curve))]
            if returns:
                avg_return = sum(returns) / len(returns)
                std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
                sharpe_ratio = (avg_return / std_return) if std_return > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        return BacktestResult(
            strategy_name=strategy_name,
            instrument=instrument,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            total_trades=total_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trades=trades
        )
    
    def _empty_result(
        self,
        strategy_name: str,
        instrument: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float
    ) -> BacktestResult:
        """Create empty result for failed backtest"""
        return BacktestResult(
            strategy_name=strategy_name,
            instrument=instrument,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            final_balance=initial_balance,
            total_pnl=0,
            total_pnl_pct=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            avg_win=0,
            avg_loss=0,
            profit_factor=0,
            max_drawdown=0,
            max_drawdown_pct=0,
            sharpe_ratio=0,
            trades=[]
        )
    
    def validate_strategy(
        self,
        strategy: BaseStrategy,
        instrument: str,
        min_days: int = 14,
        min_win_rate: float = 0.55,
        min_profit_factor: float = 1.2,
        max_drawdown_pct: float = 10.0
    ) -> Tuple[bool, BacktestResult]:
        """
        Validate strategy meets minimum requirements
        
        Returns:
            (is_valid: bool, result: BacktestResult)
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=min_days)
        
        result = self.run_backtest(strategy, instrument, start_date, end_date)
        
        is_valid = (
            result.total_trades >= 10 and  # Minimum 10 trades
            result.win_rate >= min_win_rate * 100 and
            result.profit_factor >= min_profit_factor and
            result.max_drawdown_pct <= max_drawdown_pct
        )
        
        logger.info(f"{'✅' if is_valid else '❌'} Strategy validation: {strategy.name}")
        logger.info(f"   Win rate: {result.win_rate:.1f}% (min: {min_win_rate*100:.1f}%)")
        logger.info(f"   Profit factor: {result.profit_factor:.2f} (min: {min_profit_factor:.2f})")
        logger.info(f"   Max drawdown: {result.max_drawdown_pct:.1f}% (max: {max_drawdown_pct:.1f}%)")
        logger.info(f"   Total trades: {result.total_trades}")
        
        return is_valid, result

