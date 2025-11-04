#!/bin/bash
# Startup script for Modular Trading System v2

cd "$(dirname "$0")"

echo "🚀 Starting Modular Trading System v2..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create .env file with your API keys"
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found!"
    exit 1
fi

echo "✅ Environment check passed"
echo ""

# Start trading system in background
echo "📈 Starting trading system..."
python3 main.py &
TRADING_PID=$!
echo "   Trading system PID: $TRADING_PID"
echo ""

# Wait a bit for trading system to initialize
sleep 3

# Start dashboard
echo "📊 Starting dashboard..."
echo "   Dashboard will be available at: http://localhost:5000"
echo ""
python3 dashboard_server.py &
DASHBOARD_PID=$!
echo "   Dashboard PID: $DASHBOARD_PID"
echo ""

echo "✅ Both systems started!"
echo ""
echo "To stop the systems, run:"
echo "  kill $TRADING_PID $DASHBOARD_PID"
echo ""
echo "Or press Ctrl+C to stop dashboard (trading system will continue)"
echo ""

# Wait for dashboard (foreground)
wait $DASHBOARD_PID
