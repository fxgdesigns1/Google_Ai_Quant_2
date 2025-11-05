#!/usr/bin/env python3
"""
Dashboard Flask Application
Full-featured web dashboard for monitoring and controlling the trading system
"""

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import logging
import sys
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
# Use threading mode instead of eventlet for better compatibility
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global system reference (will be set by dashboard_server.py)
system_components = None


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/strategies')
def strategies():
    """Strategy control page"""
    return render_template('strategies.html')


@app.route('/positions')
def positions():
    """Positions page"""
    return render_template('positions.html')


@app.route('/performance')
def performance():
    """Performance analytics page"""
    return render_template('performance.html')


@app.route('/settings')
def settings():
    """Settings page"""
    return render_template('settings.html')


# API Endpoints

@app.route('/api/status')
def api_status():
    """Get system status"""
    try:
        return jsonify({
            'status': 'online',
            'market_data': system_components.get('market_data').running if system_components and system_components.get('market_data') else False,
            'timestamp': str(Path(__file__).stat().st_mtime)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/accounts')
def api_accounts():
    """Get account balances"""
    try:
        # Try to get broker and config from system_components
        broker = None
        config = None
        if system_components:
            broker = system_components.get('broker')
            config = system_components.get('config')
        
        # If no config from system, try loading from file
        if not config:
            try:
                config_path = Path(__file__).parent.parent / 'config.yaml'
                if config_path.exists():
                    import yaml
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
            except Exception as e:
                logger.warning(f"Could not load config: {e}")
        
        if not config:
            return jsonify({'accounts': []})
        
        accounts_data = []
        for account_config in config.get('accounts', []):
            try:
                if broker:
                    account = broker.get_account(account_config['id'])
                    accounts_data.append({
                        'id': account_config['id'],
                        'name': account_config.get('name', account_config['id']),
                        'balance': account.balance,
                        'unrealized_pl': account.unrealized_pl,
                        'realized_pl': account.realized_pl,
                        'margin_used': account.margin_used,
                        'margin_available': account.margin_available,
                        'open_trade_count': account.open_trade_count,
                        'open_position_count': account.open_position_count
                    })
                else:
                    # Return account info from config only
                    accounts_data.append({
                        'id': account_config['id'],
                        'name': account_config.get('name', account_config['id']),
                        'balance': account_config.get('balance', 0),
                        'unrealized_pl': 0,
                        'realized_pl': 0,
                        'margin_used': 0,
                        'margin_available': account_config.get('balance', 0),
                        'open_trade_count': 0,
                        'open_position_count': 0
                    })
            except Exception as e:
                logger.error(f"Error getting account {account_config['id']}: {e}")
        
        return jsonify({'accounts': accounts_data})
    except Exception as e:
        logger.error(f"Error in api_accounts: {e}", exc_info=True)
        return jsonify({'accounts': []})


@app.route('/api/positions')
def api_positions():
    """Get open positions"""
    try:
        # Try to get broker and config from system_components
        broker = None
        config = None
        if system_components:
            broker = system_components.get('broker')
            config = system_components.get('config')
        
        # If no config from system, try loading from file
        if not config:
            try:
                config_path = Path(__file__).parent.parent / 'config.yaml'
                if config_path.exists():
                    import yaml
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
            except Exception as e:
                logger.warning(f"Could not load config: {e}")
        
        if not config or not broker:
            return jsonify({'positions': []})
        
        all_positions = []
        for account_config in config.get('accounts', []):
            try:
                positions = broker.get_open_positions(account_config['id'])
                for instrument, position in positions.items():
                    all_positions.append({
                        'account_id': account_config['id'],
                        'instrument': instrument,
                        'long_units': position.long_units,
                        'short_units': position.short_units,
                        'unrealized_pl': position.unrealized_pl,
                        'long_avg_price': position.long_avg_price,
                        'short_avg_price': position.short_avg_price
                    })
            except Exception as e:
                logger.error(f"Error getting positions for {account_config['id']}: {e}")
        
        return jsonify({'positions': all_positions})
    except Exception as e:
        logger.error(f"Error in api_positions: {e}", exc_info=True)
        return jsonify({'positions': []})


@app.route('/api/strategies')
def api_strategies():
    """Get strategy status"""
    try:
        coordinator = None
        if system_components:
            coordinator = system_components.get('strategy_coordinator')
        if coordinator:
            return jsonify({'strategies': coordinator.get_strategy_status()})
        return jsonify({'strategies': {}})
    except Exception as e:
        logger.error(f"Error getting strategies: {e}", exc_info=True)
        return jsonify({'error': str(e), 'strategies': {}}), 500


@app.route('/api/performance')
def api_performance():
    """Get comprehensive performance metrics for all accounts/strategies"""
    try:
        db_path = Path(__file__).parent.parent / 'data' / 'trades.db'
        if not db_path.exists():
            return jsonify({'performance': {}})
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get config for account mapping
        config = {}
        if system_components:
            config = system_components.get('config', {})
        else:
            # Try loading from file
            try:
                config_path = Path(__file__).parent.parent / 'config.yaml'
                if config_path.exists():
                    import yaml
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Could not load config: {e}")
        
        account_map = {acc['id']: acc.get('name', acc['id']) for acc in config.get('accounts', [])}
        
        performance_data = {}
        
        # Get performance by account
        for account_id, account_name in account_map.items():
            # Get all closed trades for this account
            cursor.execute('''
                SELECT * FROM trades 
                WHERE account_id = ? AND status = 'CLOSED'
                ORDER BY exit_time DESC
            ''', (account_id,))
            trades = [dict(row) for row in cursor.fetchall()]
            
            if not trades:
                continue
            
            # Calculate metrics
            total_trades = len(trades)
            winning_trades = [t for t in trades if t['pnl'] > 0]
            losing_trades = [t for t in trades if t['pnl'] <= 0]
            win_count = len(winning_trades)
            loss_count = len(losing_trades)
            win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
            
            total_pnl = sum(t['pnl'] for t in trades)
            total_pnl_pct = sum(t['pnl_pct'] for t in trades)
            avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
            avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            # Profit factor
            gross_profit = sum(t['pnl'] for t in winning_trades) if winning_trades else 0
            gross_loss = abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
            
            # Expectancy
            expectancy = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * abs(avg_loss))
            
            # Drawdown calculation
            cumulative_pnl = 0
            peak = 0
            max_drawdown = 0
            for trade in sorted(trades, key=lambda x: x['exit_time']):
                cumulative_pnl += trade['pnl']
                if cumulative_pnl > peak:
                    peak = cumulative_pnl
                drawdown = peak - cumulative_pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            # Sharpe ratio (simplified - using returns)
            returns = [t['pnl_pct'] for t in trades]
            if len(returns) > 1:
                avg_return = sum(returns) / len(returns)
                variance = sum((r - avg_return) ** 2 for r in returns) / (len(returns) - 1)
                std_dev = variance ** 0.5
                sharpe = (avg_return / std_dev * (252 ** 0.5)) if std_dev > 0 else 0  # Annualized
            else:
                sharpe = 0
            
            # Strategy breakdown
            strategy_stats = {}
            cursor.execute('''
                SELECT strategy_name, COUNT(*) as count, SUM(pnl) as total_pnl,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
                FROM trades 
                WHERE account_id = ? AND status = 'CLOSED'
                GROUP BY strategy_name
            ''', (account_id,))
            for row in cursor.fetchall():
                strategy_stats[row['strategy_name']] = {
                    'total_trades': row['count'],
                    'win_count': row['wins'],
                    'win_rate': (row['wins'] / row['count'] * 100) if row['count'] > 0 else 0,
                    'total_pnl': row['total_pnl']
                }
            
            performance_data[account_id] = {
                'account_name': account_name,
                'total_trades': total_trades,
                'win_count': win_count,
                'loss_count': loss_count,
                'win_rate': round(win_rate, 2),
                'total_pnl': round(total_pnl, 2),
                'total_pnl_pct': round(total_pnl_pct, 2),
                'avg_pnl': round(avg_pnl, 2),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'profit_factor': round(profit_factor, 2),
                'expectancy': round(expectancy, 2),
                'max_drawdown': round(max_drawdown, 2),
                'sharpe_ratio': round(sharpe, 2),
                'strategy_stats': strategy_stats
            }
        
        conn.close()
        return jsonify({'performance': performance_data})
    except Exception as e:
        logger.error(f"Error getting performance: {e}", exc_info=True)
        return jsonify({'error': str(e), 'performance': {}}), 500


@app.route('/api/sentiment')
def api_sentiment():
    """Get market sentiment"""
    try:
        news_aggregator = None
        if system_components:
            news_aggregator = system_components.get('news_aggregator')
        
        if not news_aggregator or not news_aggregator.is_enabled():
            return jsonify({'sentiment': {}, 'enabled': False})
        
        sentiment = news_aggregator.fetch_sentiment(window_minutes=10)
        if sentiment:
            return jsonify({
                'sentiment': sentiment,
                'enabled': True,
                'timestamp': datetime.utcnow().isoformat()
            })
        else:
            return jsonify({'sentiment': {}, 'enabled': False})
    except Exception as e:
        logger.error(f"Error getting sentiment: {e}", exc_info=True)
        return jsonify({'sentiment': {}, 'enabled': False})


@app.route('/api/strategy/<strategy_name>/enable', methods=['POST'])
def enable_strategy(strategy_name):
    """Enable a strategy"""
    try:
        coordinator = None
        if system_components:
            coordinator = system_components.get('strategy_coordinator')
        if coordinator:
            for strategy in coordinator.strategies:
                if strategy.get_name() == strategy_name:
                    strategy.enable()
                    return jsonify({'success': True})
        return jsonify({'error': 'Strategy not found or system not initialized'}), 404
    except Exception as e:
        logger.error(f"Error enabling strategy: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/strategy/<strategy_name>/disable', methods=['POST'])
def disable_strategy(strategy_name):
    """Disable a strategy"""
    try:
        coordinator = None
        if system_components:
            coordinator = system_components.get('strategy_coordinator')
        if coordinator:
            for strategy in coordinator.strategies:
                if strategy.get_name() == strategy_name:
                    strategy.disable()
                    return jsonify({'success': True})
        return jsonify({'error': 'Strategy not found or system not initialized'}), 404
    except Exception as e:
        logger.error(f"Error disabling strategy: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/news/events')
def api_news_events():
    """Get upcoming news events"""
    try:
        news_aggregator = None
        if system_components:
            news_aggregator = system_components.get('news_aggregator')
        if not news_aggregator or not news_aggregator.is_enabled():
            return jsonify({'events': [], 'enabled': False})
        
        events = news_aggregator.get_all_events(hours_ahead=24)
        events_data = []
        for event in events:
            events_data.append({
                'time_utc': event.time_utc.isoformat(),
                'country': event.country,
                'title': event.title,
                'impact': event.impact,
                'currency': event.currency,
                'forecast': event.forecast,
                'actual': event.actual,
                'source': event.source,
                'is_high_impact': event.is_high_impact(),
                'impacted_instruments': event.get_impacted_instruments()
            })
        
        return jsonify({
            'events': events_data,
            'enabled': True,
            'last_refresh': news_aggregator.last_refresh.isoformat() if news_aggregator.last_refresh else None
        })
    except Exception as e:
        logger.error(f"Error getting news events: {e}", exc_info=True)
        return jsonify({'events': [], 'error': str(e), 'enabled': False}), 500


@app.route('/api/news/upcoming')
def api_news_upcoming():
    """Get upcoming high-impact news events"""
    try:
        news_aggregator = None
        if system_components:
            news_aggregator = system_components.get('news_aggregator')
        if not news_aggregator or not news_aggregator.is_enabled():
            return jsonify({'events': [], 'enabled': False})
        
        upcoming = news_aggregator.get_upcoming_high_impact()
        events_data = []
        for event in upcoming:
            from datetime import datetime
            minutes_until = (event.time_utc - datetime.utcnow()).total_seconds() / 60
            events_data.append({
                'time_utc': event.time_utc.isoformat(),
                'country': event.country,
                'title': event.title,
                'impact': event.impact,
                'currency': event.currency,
                'minutes_until': int(minutes_until),
                'impacted_instruments': event.get_impacted_instruments()
            })
        
        return jsonify({
            'events': events_data,
            'enabled': True,
            'pause_before_minutes': news_aggregator.pause_before_high_impact
        })
    except Exception as e:
        logger.error(f"Error getting upcoming news: {e}")
        return jsonify({'events': [], 'error': str(e)}), 500


@app.route('/api/recent-trades')
def api_recent_trades():
    """Get recent closed trades"""
    try:
        db_path = Path(__file__).parent.parent / 'data' / 'trades.db'
        if not db_path.exists():
            return jsonify({'trades': []})
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            WHERE status = 'CLOSED'
            ORDER BY exit_time DESC
            LIMIT 100
        ''')
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({'trades': trades})
    except Exception as e:
        logger.error(f"Error getting recent trades: {e}", exc_info=True)
        return jsonify({'trades': [], 'error': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    logger.info('Client connected')
    emit('status', {'message': 'Connected to trading system'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    logger.info('Client disconnected')


def set_system_components(components):
    """Set system components reference (called by dashboard_server.py)"""
    global system_components
    system_components = components
