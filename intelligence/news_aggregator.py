#!/usr/bin/env python3
"""
News Aggregator
Fetches economic calendars from TradingEconomics and Finnhub
Provides news event detection and trading halt functionality
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NewsEvent:
    """Economic news event"""
    time_utc: datetime
    country: str
    title: str
    impact: str  # 'high', 'medium', 'low'
    currency: str
    forecast: Optional[float] = None
    actual: Optional[float] = None
    source: str = "unknown"  # 'tradingeconomics' or 'finnhub'
    
    def is_high_impact(self) -> bool:
        """Check if event is high impact"""
        return 'high' in self.impact.lower() or 'importance:high' in self.impact.lower()
    
    def get_impacted_instruments(self) -> List[str]:
        """Get list of trading instruments affected by this event"""
        mapping = {
            'USD': ['EUR_USD', 'GBP_USD', 'XAU_USD', 'USD_JPY', 'AUD_USD', 'USD_CAD', 'NZD_USD'],
            'EUR': ['EUR_USD', 'EUR_GBP', 'EUR_JPY'],
            'GBP': ['GBP_USD', 'EUR_GBP', 'GBP_JPY'],
            'JPY': ['USD_JPY', 'EUR_JPY', 'GBP_JPY'],
            'AUD': ['AUD_USD', 'AUD_JPY'],
            'CAD': ['USD_CAD'],
            'NZD': ['NZD_USD'],
        }
        return mapping.get(self.currency.upper(), [])


class NewsAggregator:
    """
    Fetches economic calendars from TradingEconomics and Finnhub
    Provides interface for event detection and trading halts
    """
    
    def __init__(self, config: Dict = None):
        """Initialize news aggregator"""
        config = config or {}
        news_config = config.get('news', {})
        
        # API keys from environment or config
        self.tradingeconomics_key = os.getenv('TRADINGECONOMICS_KEY', '')
        self.finnhub_key = os.getenv('FINNHUB_KEY', '')
        self.marketaux_key = os.getenv('MARKETAUX_KEY', '')
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_KEY', '')
        
        # Configuration
        self.enabled = news_config.get('enabled', True)
        self.pause_before_high_impact = news_config.get('pause_before_high_impact', 30)  # minutes
        self.update_interval_minutes = news_config.get('update_interval_minutes', 15)
        
        # Cache
        self.cached_events: List[NewsEvent] = []
        self.last_refresh: Optional[datetime] = None
        self.last_sentiment: Optional[Dict[str, Any]] = None
        self.last_sentiment_time: Optional[datetime] = None
        
        if self.enabled and self.is_enabled():
            logger.info("✅ News Aggregator initialized")
            logger.info(f"   TradingEconomics: {'✅' if self.tradingeconomics_key else '❌'}")
            logger.info(f"   Finnhub: {'✅' if self.finnhub_key else '❌'}")
            logger.info(f"   Pause before high-impact: {self.pause_before_high_impact} minutes")
        else:
            logger.warning("⚠️ News Aggregator disabled or no API keys")
    
    def is_enabled(self) -> bool:
        """Check if news aggregator has API keys"""
        return bool(self.tradingeconomics_key or self.finnhub_key)
    
    def refresh_calendar(self) -> List[NewsEvent]:
        """Refresh economic calendar from all sources"""
        if not self.is_enabled():
            return []
        
        try:
            events: List[NewsEvent] = []
            now = datetime.utcnow()
            start = (now - timedelta(hours=1)).strftime('%Y-%m-%d')
            end = (now + timedelta(days=1)).strftime('%Y-%m-%d')
            
            # TradingEconomics
            if self.tradingeconomics_key:
                try:
                    te_url = f"https://api.tradingeconomics.com/calendar?d1={start}&d2={end}&format=json&c={self.tradingeconomics_key}"
                    r = requests.get(te_url, timeout=10)
                    if r.status_code == 200:
                        for e in r.json():
                            try:
                                date_str = e.get('Date', '')
                                if 'T' in date_str:
                                    t = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
                                else:
                                    t = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                                
                                impact = (e.get('Importance', '') or '').lower()
                                events.append(
                                    NewsEvent(
                                        time_utc=t,
                                        country=e.get('Country', ''),
                                        title=e.get('Event', ''),
                                        impact=impact,
                                        currency=e.get('Currency', ''),
                                        forecast=self._to_float(e.get('Forecast')),
                                        actual=self._to_float(e.get('Actual')),
                                        source='tradingeconomics'
                                    )
                                )
                            except Exception as ex:
                                logger.debug(f"Error parsing TradingEconomics event: {ex}")
                                continue
                    else:
                        logger.warning(f"TradingEconomics API returned {r.status_code}")
                except Exception as ex:
                    logger.warning(f"TradingEconomics calendar failed: {ex}")
            
            # Finnhub
            if self.finnhub_key:
                try:
                    fh_url = f"https://finnhub.io/api/v1/calendar/economic?from={start}&to={end}&token={self.finnhub_key}"
                    r = requests.get(fh_url, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        for e in data.get('economicCalendar', []):
                            try:
                                date_str = e.get('time', '') or f"{e.get('date', '')} 12:00:00"
                                t = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                                impact = (e.get('impact', '') or '').lower()
                                
                                events.append(
                                    NewsEvent(
                                        time_utc=t,
                                        country=e.get('country', ''),
                                        title=e.get('event', ''),
                                        impact=impact,
                                        currency=e.get('currency', ''),
                                        forecast=self._to_float(e.get('estimate')),
                                        actual=self._to_float(e.get('actual')),
                                        source='finnhub'
                                    )
                                )
                            except Exception as ex:
                                logger.debug(f"Error parsing Finnhub event: {ex}")
                                continue
                    else:
                        logger.warning(f"Finnhub API returned {r.status_code}")
                except Exception as ex:
                    logger.warning(f"Finnhub calendar failed: {ex}")
            
            # Remove duplicates and sort
            unique_events = {}
            for event in events:
                # Use time + title as unique key
                key = (event.time_utc, event.title)
                if key not in unique_events or event.is_high_impact():
                    unique_events[key] = event
            
            self.cached_events = sorted(unique_events.values(), key=lambda x: x.time_utc)
            self.last_refresh = datetime.utcnow()
            
            logger.info(f"📰 Refreshed calendar: {len(self.cached_events)} events")
            return self.cached_events
            
        except Exception as e:
            logger.error(f"❌ Calendar refresh error: {e}", exc_info=True)
            return []
    
    def get_upcoming_high_impact(self, within_minutes: int = None) -> List[NewsEvent]:
        """Get upcoming high-impact news events"""
        if within_minutes is None:
            within_minutes = self.pause_before_high_impact + 30  # Default window
        
        # Refresh if needed
        if not self.last_refresh or (datetime.utcnow() - self.last_refresh) > timedelta(minutes=self.update_interval_minutes):
            self.refresh_calendar()
        
        now = datetime.utcnow()
        horizon = now + timedelta(minutes=within_minutes)
        
        high_impact = [
            e for e in self.cached_events 
            if e.time_utc >= now 
            and e.time_utc <= horizon 
            and e.is_high_impact()
        ]
        
        return high_impact
    
    def should_pause_trading(self, instrument: str = None) -> tuple:
        """
        Check if trading should be paused due to upcoming high-impact news
        
        Returns:
            (should_pause: bool, reason: str or None)
        """
        if not self.enabled or not self.is_enabled():
            return False, None
        
        upcoming = self.get_upcoming_high_impact(within_minutes=self.pause_before_high_impact + 5)
        
        if not upcoming:
            return False, None
        
        now = datetime.utcnow()
        
        for event in upcoming:
            # Check if event is within pause window
            minutes_until = (event.time_utc - now).total_seconds() / 60
            
            if 0 <= minutes_until <= self.pause_before_high_impact:
                # If instrument specified, check if it's affected
                if instrument:
                    affected = event.get_impacted_instruments()
                    if instrument not in affected:
                        continue
                
                reason = f"High-impact news: {event.title} ({event.country} {event.currency}) in {int(minutes_until)} minutes"
                return True, reason
        
        return False, None
    
    def get_events_for_instrument(self, instrument: str, hours_ahead: int = 24) -> List[NewsEvent]:
        """Get news events affecting a specific instrument"""
        if not self.last_refresh or (datetime.utcnow() - self.last_refresh) > timedelta(minutes=self.update_interval_minutes):
            self.refresh_calendar()
        
        now = datetime.utcnow()
        horizon = now + timedelta(hours=hours_ahead)
        
        relevant_events = []
        for event in self.cached_events:
            if event.time_utc >= now and event.time_utc <= horizon:
                if instrument in event.get_impacted_instruments():
                    relevant_events.append(event)
        
        return relevant_events
    
    def surprise_score(self, event: NewsEvent) -> Optional[float]:
        """Calculate surprise score (actual vs forecast)"""
        if event.actual is None or event.forecast is None:
            return None
        
        try:
            # Normalized surprise: (actual - forecast) / |forecast|
            denominator = max(1e-9, abs(event.forecast))
            return (event.actual - event.forecast) / denominator
        except Exception:
            return None
    
    def fetch_sentiment(self, window_minutes: int = 10) -> Optional[Dict[str, Any]]:
        """
        Fetch market sentiment from news sources
        Returns dict with avg_score, count, entity_hits per currency
        """
        if not self.marketaux_key:
            return None
        
        try:
            now = datetime.utcnow()
            
            # Cache sentiment for 2 minutes
            if self.last_sentiment and self.last_sentiment_time:
                if (now - self.last_sentiment_time) < timedelta(minutes=2):
                    return self.last_sentiment
            
            since = (now - timedelta(minutes=window_minutes)).isoformat() + 'Z'
            total_score = 0.0
            total_count = 0
            entities: Dict[str, int] = {
                'USD': 0, 'EUR': 0, 'GBP': 0, 'JPY': 0, 'AUD': 0, 
                'CAD': 0, 'NZD': 0, 'XAU': 0
            }
            
            # Marketaux
            if self.marketaux_key:
                try:
                    query = 'forex OR fx OR currency OR gold OR xau'
                    url = f"https://api.marketaux.com/v1/news/all?filter_entities=true&limit=25&published_after={since}&language=en&api_token={self.marketaux_key}&query={query}"
                    r = requests.get(url, timeout=10)
                    if r.status_code == 200:
                        for item in r.json().get('data', []):
                            score = item.get('sentiment_score')
                            if isinstance(score, (int, float)):
                                total_score += float(score)
                                total_count += 1
                            
                            # Count entity mentions
                            for ent in (item.get('entities') or []):
                                sym = (ent.get('symbol') or '').upper()
                                name = (ent.get('name') or '').upper()
                                text = f"{sym} {name}"
                                
                                for currency in entities.keys():
                                    if currency in text:
                                        entities[currency] += 1
                except Exception as ex:
                    logger.debug(f"Marketaux sentiment failed: {ex}")
            
            avg_score = (total_score / max(1, total_count)) if total_count else 0.0
            result = {
                'avg_score': avg_score,
                'count': total_count,
                'entities': entities,
                'timestamp': now.isoformat()
            }
            
            self.last_sentiment = result
            self.last_sentiment_time = now
            return result
            
        except Exception as e:
            logger.warning(f"fetch_sentiment error: {e}")
            return None
    
    @staticmethod
    def _to_float(val: Any) -> Optional[float]:
        """Convert value to float, handling None and percentages"""
        try:
            if val is None:
                return None
            val_str = str(val).replace('%', '').replace(',', '').strip()
            return float(val_str)
        except Exception:
            return None
    
    def get_all_events(self, hours_ahead: int = 24) -> List[NewsEvent]:
        """Get all events in the next N hours"""
        if not self.last_refresh or (datetime.utcnow() - self.last_refresh) > timedelta(minutes=self.update_interval_minutes):
            self.refresh_calendar()
        
        now = datetime.utcnow()
        horizon = now + timedelta(hours=hours_ahead)
        
        return [e for e in self.cached_events if e.time_utc >= now and e.time_utc <= horizon]

