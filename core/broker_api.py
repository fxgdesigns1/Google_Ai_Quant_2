#!/usr/bin/env python3
"""
OANDA Broker API Client
Single interface to OANDA API with connection management, rate limiting, and error handling
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from oandapyV20 import API
from oandapyV20.endpoints import accounts, pricing, orders, trades, positions, instruments
from oandapyV20.exceptions import V20Error

logger = logging.getLogger(__name__)


@dataclass
class HistoricalCandle:
    """Historical price candle"""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class BrokerAccount:
    """Account information"""
    account_id: str
    balance: float
    unrealized_pl: float
    realized_pl: float
    margin_used: float
    margin_available: float
    open_trade_count: int
    open_position_count: int
    currency: str = "USD"


@dataclass
class BrokerPrice:
    """Market price data"""
    instrument: str
    bid: float
    ask: float
    spread: float
    timestamp: datetime
    time: str


@dataclass
class BrokerOrder:
    """Order information"""
    order_id: str
    instrument: str
    units: int
    side: str  # 'buy' or 'sell'
    type: str  # 'MARKET', 'LIMIT', 'STOP'
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: str = "PENDING"
    fill_time: Optional[datetime] = None
    trade_id: Optional[str] = None


@dataclass
class BrokerPosition:
    """Position information"""
    instrument: str
    long_units: int = 0
    short_units: int = 0
    long_unrealized_pl: float = 0.0
    short_unrealized_pl: float = 0.0
    unrealized_pl: float = 0.0
    margin_used: float = 0.0
    long_avg_price: Optional[float] = None
    short_avg_price: Optional[float] = None


class OandaBroker:
    """OANDA API Client with rate limiting and error handling"""
    
    def __init__(self, api_key: str = None, account_id: str = None, environment: str = None):
        """Initialize OANDA broker client"""
        self.api_key = api_key or os.getenv('OANDA_API_KEY')
        self.account_id = account_id
        self.environment = environment or os.getenv('OANDA_ENVIRONMENT', 'practice')
        
        if not self.api_key:
            raise ValueError("OANDA_API_KEY not found in environment")
        
        # Initialize OANDA API client
        self.api = API(access_token=self.api_key, environment=self.environment)
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
        
        # Connection status
        self.is_connected = False
        self.connection_retries = 0
        self.max_retries = 3
        
        logger.info(f"✅ OANDA broker initialized for {self.environment} environment")
        
        # Test connection
        self._test_connection()
    
    def _rate_limit(self):
        """Enforce rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _test_connection(self):
        """Test connection to OANDA API"""
        try:
            if not self.account_id:
                return
            self._rate_limit()
            r = accounts.AccountSummary(accountID=self.account_id)
            self.api.request(r)
            self.is_connected = True
            logger.info("✅ OANDA connection successful")
        except Exception as e:
            logger.warning(f"⚠️ OANDA connection test failed: {e}")
            self.is_connected = False
    
    def get_account(self, account_id: str = None) -> BrokerAccount:
        """Get account information"""
        account_id = account_id or self.account_id
        if not account_id:
            raise ValueError("Account ID required")
        
        try:
            self._rate_limit()
            r = accounts.AccountSummary(accountID=account_id)
            response = self.api.request(r)
            account = response.get('account', {})
            
            return BrokerAccount(
                account_id=account_id,
                balance=float(account.get('balance', 0)),
                unrealized_pl=float(account.get('unrealizedPL', 0)),
                realized_pl=float(account.get('realizedPL', 0)),
                margin_used=float(account.get('marginUsed', 0)),
                margin_available=float(account.get('marginAvailable', 0)),
                open_trade_count=int(account.get('openTradeCount', 0)),
                open_position_count=int(account.get('openPositionCount', 0)),
                currency=account.get('currency', 'USD')
            )
        except V20Error as e:
            logger.error(f"❌ Failed to get account {account_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error getting account: {e}")
            raise
    
    def get_prices(self, instruments: List[str], account_id: str = None) -> Dict[str, BrokerPrice]:
        """Get current prices for instruments"""
        account_id = account_id or self.account_id
        if not account_id:
            raise ValueError("Account ID required")
        
        try:
            self._rate_limit()
            r = pricing.PricingInfo(accountID=account_id, params={'instruments': ','.join(instruments)})
            response = self.api.request(r)
            
            prices = {}
            for price_info in response.get('prices', []):
                instrument = price_info.get('instrument')
                bids = price_info.get('bids', [])
                asks = price_info.get('asks', [])
                
                if bids and asks:
                    bid = float(bids[0].get('price', 0))
                    ask = float(asks[0].get('price', 0))
                    spread = ask - bid
                    time_str = price_info.get('time', '')
                    
                    # Parse timestamp
                    try:
                        timestamp = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    except:
                        timestamp = datetime.utcnow()
                    
                    prices[instrument] = BrokerPrice(
                        instrument=instrument,
                        bid=bid,
                        ask=ask,
                        spread=spread,
                        timestamp=timestamp,
                        time=time_str
                    )
            
            return prices
        except V20Error as e:
            logger.error(f"❌ Failed to get prices: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error getting prices: {e}")
            raise
    
    def place_market_order(
        self,
        instrument: str,
        units: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        account_id: str = None
    ) -> BrokerOrder:
        """Place a market order"""
        account_id = account_id or self.account_id
        if not account_id:
            raise ValueError("Account ID required")
        
        try:
            self._rate_limit()
            
            order_data = {
                "order": {
                    "instrument": instrument,
                    "units": str(units),
                    "type": "MARKET"
                }
            }
            
            # Add stop loss if provided
            if stop_loss:
                order_data["order"]["stopLossOnFill"] = {
                    "price": str(round(stop_loss, 5))
                }
            
            # Add take profit if provided
            if take_profit:
                order_data["order"]["takeProfitOnFill"] = {
                    "price": str(round(take_profit, 5))
                }
            
            r = orders.OrderCreate(accountID=account_id, data=order_data)
            response = self.api.request(r)
            
            order_response = response.get('orderFillTransaction') or response.get('orderCreateTransaction', {})
            trade_id = order_response.get('tradeOpened', {}).get('tradeID')
            
            return BrokerOrder(
                order_id=order_response.get('id', ''),
                instrument=instrument,
                units=units,
                side='buy' if units > 0 else 'sell',
                type='MARKET',
                price=float(order_response.get('price', 0)) if order_response.get('price') else None,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status='FILLED' if trade_id else 'PENDING',
                fill_time=datetime.utcnow() if trade_id else None,
                trade_id=trade_id
            )
        except V20Error as e:
            logger.error(f"❌ Failed to place market order: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error placing order: {e}")
            raise
    
    def close_trade(self, trade_id: str, account_id: str = None) -> Dict[str, Any]:
        """Close a trade"""
        account_id = account_id or self.account_id
        if not account_id:
            raise ValueError("Account ID required")
        
        try:
            self._rate_limit()
            r = trades.TradeClose(accountID=account_id, tradeID=trade_id)
            response = self.api.request(r)
            logger.info(f"✅ Trade {trade_id} closed")
            return response
        except V20Error as e:
            logger.error(f"❌ Failed to close trade {trade_id}: {e}")
            raise
    
    def get_open_trades(self, account_id: str = None) -> List[Dict[str, Any]]:
        """Get all open trades"""
        account_id = account_id or self.account_id
        if not account_id:
            raise ValueError("Account ID required")
        
        try:
            self._rate_limit()
            r = trades.OpenTrades(accountID=account_id)
            response = self.api.request(r)
            return response.get('trades', [])
        except V20Error as e:
            logger.error(f"❌ Failed to get open trades: {e}")
            raise
    
    def get_open_positions(self, account_id: str = None) -> Dict[str, BrokerPosition]:
        """Get all open positions"""
        account_id = account_id or self.account_id
        if not account_id:
            raise ValueError("Account ID required")
        
        try:
            self._rate_limit()
            r = positions.OpenPositions(accountID=account_id)
            response = self.api.request(r)
            
            positions_dict = {}
            for pos_data in response.get('positions', []):
                instrument = pos_data.get('instrument')
                long_units = int(pos_data.get('long', {}).get('units', 0))
                short_units = abs(int(pos_data.get('short', {}).get('units', 0)))
                
                positions_dict[instrument] = BrokerPosition(
                    instrument=instrument,
                    long_units=long_units,
                    short_units=short_units,
                    long_unrealized_pl=float(pos_data.get('long', {}).get('unrealizedPL', 0)),
                    short_unrealized_pl=float(pos_data.get('short', {}).get('unrealizedPL', 0)),
                    unrealized_pl=float(pos_data.get('unrealizedPL', 0)),
                    margin_used=float(pos_data.get('marginUsed', 0)),
                    long_avg_price=float(pos_data.get('long', {}).get('averagePrice', 0)) if pos_data.get('long', {}).get('averagePrice') else None,
                    short_avg_price=float(pos_data.get('short', {}).get('averagePrice', 0)) if pos_data.get('short', {}).get('averagePrice') else None
                )
            
            return positions_dict
        except V20Error as e:
            logger.error(f"❌ Failed to get open positions: {e}")
            raise
    
    def modify_trade(
        self,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        account_id: str = None
    ) -> Dict[str, Any]:
        """Modify stop loss or take profit on a trade"""
        account_id = account_id or self.account_id
        if not account_id:
            raise ValueError("Account ID required")
        
        try:
            self._rate_limit()
            
            data = {}
            if stop_loss is not None:
                data['stopLoss'] = {'price': str(round(stop_loss, 5))}
            if take_profit is not None:
                data['takeProfit'] = {'price': str(round(take_profit, 5))}
            
            r = trades.TradeCRCDO(accountID=account_id, tradeID=trade_id, data=data)
            response = self.api.request(r)
            logger.info(f"✅ Trade {trade_id} modified")
            return response
        except V20Error as e:
            logger.error(f"❌ Failed to modify trade {trade_id}: {e}")
            raise
    
    def get_historical_candles(
        self,
        instrument: str,
        granularity: str = 'M15',
        count: int = 50,
        account_id: str = None
    ) -> List[HistoricalCandle]:
        """
        Fetch historical candles from OANDA
        
        Args:
            instrument: Instrument symbol (e.g., 'EUR_USD', 'XAU_USD')
            granularity: Timeframe (M1, M5, M15, H1, H4, D, etc.)
            count: Number of candles to fetch (max 5000)
            account_id: Account ID (optional, uses default if not provided)
        
        Returns:
            List of HistoricalCandle objects
        """
        account_id = account_id or self.account_id
        if not account_id:
            raise ValueError("Account ID required")
        
        try:
            self._rate_limit()
            
            params = {
                'granularity': granularity,
                'count': min(count, 5000)  # OANDA max is 5000
            }
            
            r = instruments.InstrumentsCandles(instrument=instrument, params=params)
            response = self.api.request(r)
            
            candles = []
            for candle_data in response.get('candles', []):
                if candle_data.get('complete', False):  # Only use complete candles
                    mid = candle_data.get('mid', {})
                    time_str = candle_data.get('time', '')
                    
                    # Parse timestamp
                    try:
                        candle_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    except:
                        candle_time = datetime.utcnow()
                    
                    candle = HistoricalCandle(
                        time=candle_time,
                        open=float(mid.get('o', 0)),
                        high=float(mid.get('h', 0)),
                        low=float(mid.get('l', 0)),
                        close=float(mid.get('c', 0)),
                        volume=float(candle_data.get('volume', 0))
                    )
                    candles.append(candle)
            
            logger.debug(f"✅ Fetched {len(candles)} historical candles for {instrument}")
            return candles
            
        except V20Error as e:
            logger.error(f"❌ Failed to get historical candles for {instrument}: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Unexpected error getting historical candles: {e}")
            raise
