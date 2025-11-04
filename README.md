# Modular Trading System v2

A clean, modular, fault-isolated trading system built from scratch.

## Features

- **Modular Architecture**: Each component is independent and replaceable
- **Fault Isolation**: One broken component doesn't crash the whole system
- **Full Dashboard**: Web-based control center with real-time monitoring
- **Risk Management**: Comprehensive pre-trade checks and circuit breakers
- **News Integration**: Economic calendar and sentiment analysis
- **Strategy Framework**: Easy to add/remove/modify strategies

## Setup

### 1. Install Dependencies

```bash
cd /Users/mac/Documents/Google_quant_2
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Configure Accounts

Edit `config.yaml` to set up your accounts and strategies.

### 4. Run the System

**Terminal 1 - Trading System:**
```bash
python main.py
```

**Terminal 2 - Dashboard:**
```bash
python dashboard_server.py
```

**Access Dashboard:**
```
Open http://localhost:5000 in your browser
```

## Project Structure

```
Google_quant_2/
├── core/              # Core infrastructure (broker, data, risk, execution)
├── strategies/        # Trading strategies (one per file)
├── intelligence/      # News, sentiment, market regime
├── orchestrator/      # Strategy coordinator, position manager
├── database/          # Trade logging, backtesting
├── monitoring/        # Telegram alerts, dashboard API
├── dashboard/         # Web dashboard (Flask app)
└── data/              # SQLite databases, backtest results
```

## Configuration

All configuration is in `config.yaml`. No environment variable overrides - YAML is the single source of truth.

## Development Status

This is a clean rebuild. Start with one strategy, backtest thoroughly, then scale up.

## License

Private project - your trading system.
