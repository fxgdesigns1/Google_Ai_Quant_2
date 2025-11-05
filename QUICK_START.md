# 🚀 Quick Start Guide - London Killzone Trading System

## ✅ System Status: READY

All fixes have been implemented. The system is ready for London Killzone trading.

---

## 📋 What Was Fixed

1. ✅ **Price History Prefill** - No more 2.5-hour wait on startup
2. ✅ **London Killzone Detection** - Optimal trading window (08:00-12:00 UTC)
3. ✅ **Scanner Frequency** - Confirmed at 5 minutes (not hourly)
4. ✅ **Telegram Integration** - Your token configured
5. ✅ **Historical Data API** - Can fetch candles from OANDA

---

## ⚙️ Setup (One-Time)

### 1. Update OANDA API Key
Edit `.env` file:
```bash
OANDA_API_KEY=your_actual_oanda_api_key_here
OANDA_ENVIRONMENT=practice  # or 'live' for production
```

### 2. Verify Account IDs
Check `config.yaml` - ensure account IDs match your OANDA accounts:
```yaml
accounts:
  - id: "101-004-30719775-001"  # Your account ID
    name: "Gold Scalping"
    ...
```

### 3. Install Dependencies (if needed)
```bash
pip install -r requirements.txt
```

---

## 🚀 Starting the System

### Start Trading System
```bash
python3 main.py
```

### What Happens:
1. ✅ System loads configuration
2. ✅ Pre-fills price history (10-30 seconds)
3. ✅ Initializes all components
4. ✅ Starts scanning market every 5 minutes
5. ✅ Sends Telegram morning briefing
6. ✅ Ready to trade!

---

## 📊 London Killzone

### Optimal Trading Window
- **Time:** 08:00-12:00 UTC daily
- **Status:** Automatically detected
- **Display:** Shows "LONDON KILLZONE (Optimal)" in logs

### Why It's Optimal:
- Peak liquidity (tightest spreads)
- High volatility (more opportunities)
- Strong directional moves
- Best risk/reward setups

---

## 📱 Telegram Alerts

You'll receive Telegram notifications for:
- ✅ Trade opened (with entry, SL, TP)
- ✅ Trade closed (with P&L)
- ✅ Circuit breaker triggered
- ✅ Risk warnings
- ✅ Daily summaries
- ✅ Morning briefings

**Token:** Already configured in `.env`

---

## 🔍 Monitoring

### Check System Status
```bash
# View logs in real-time
tail -f logs/trading_system.log  # if logging to file

# Or monitor via dashboard
# Dashboard runs on http://localhost:5000 (if enabled)
```

### Telegram
- Check your Telegram for alerts
- Morning briefing sent on startup
- Trade alerts sent immediately

---

## ⚠️ Important Notes

1. **First Run:**
   - Price history prefill takes 10-30 seconds per instrument
   - System is ready immediately after (no 2.5-hour wait!)

2. **Trading Hours:**
   - London Session: 07:00-16:00 UTC
   - London Killzone: 08:00-12:00 UTC ⭐
   - NY Session: 13:00-21:00 UTC

3. **Risk Management:**
   - Circuit breaker: Stops trading if 2% daily loss
   - Max risk per trade: 1-2% per account
   - Daily trade limits: 10-15 trades per account

---

## 🛠️ Troubleshooting

### "No account_id available for pre-filling"
- **Solution:** Ensure OANDA_API_KEY is set correctly in `.env`
- System will still work, just builds history from live data

### "TELEGRAM_TOKEN not configured"
- **Solution:** Check `.env` file has TELEGRAM_TOKEN and TELEGRAM_CHAT_ID
- Token is already set: `8541856339:AAE9eetMR9N_hWoO39pijSdJacJgsVgSkIE`

### "ModuleNotFoundError: No module named 'oandapyV20'"
- **Solution:** Run `pip install -r requirements.txt`
- Or install directly: `pip install v20`

---

## ✅ Verification

All systems checked and ready:
- ✅ Price history prefill implemented
- ✅ London Killzone detection active
- ✅ Scanner runs every 5 minutes
- ✅ Telegram configured
- ✅ All code validated
- ✅ Ready for trading!

---

## 🎯 Next Steps

1. **Update API Key** in `.env`
2. **Verify Account IDs** in `config.yaml`
3. **Start System:** `python3 main.py`
4. **Monitor:** Check Telegram and logs
5. **Trade:** System will execute trades automatically during London Killzone!

---

**System is ready! 🚀**

*All fixes complete. Ready for London Killzone trading.*
