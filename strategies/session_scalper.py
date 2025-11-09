#!/usr/bin/env python3
"""
Session Scalper Strategy
=========================

Multi-pair, session-aware scalping strategy that targets at least three setups
per session while enforcing a minimum 2:1 reward-to-risk ratio.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, time
from typing import Any, Dict, List, Mapping, Optional

from .base_strategy import BaseStrategy
from core.order_executor import TradeSignal

logger = logging.getLogger(__name__)


def _parse_time(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except Exception as exc:
        raise ValueError(f"Invalid time value '{value}' (expected HH:MM)") from exc


class SessionScalperStrategy(BaseStrategy):
    """Session-based multi-pair scalping strategy."""

    DEFAULT_SESSIONS = {
        "london": ("07:00", "11:59"),
        "ny": ("12:00", "20:59"),
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.lookback_bars = config.get("lookback_bars", 150)
        self.trend_period_fast = config.get("trend_period_fast", 9)
        self.trend_period_slow = config.get("trend_period_slow", 21)
        self.base_stop_atr = config.get("base_stop_atr", 1.35)
        self.base_rr = max(2.0, config.get("target_rr", 2.2))
        self.pullback_atr_min = config.get("pullback_atr_min", 0.6)
        self.pullback_atr_max = config.get("pullback_atr_max", 2.1)
        self.momentum_threshold = config.get("momentum_threshold", 0.18)
        self.min_confidence = config.get("min_confidence", 0.55)
        self.max_confidence = config.get("max_confidence", 0.9)
        self.max_setups_per_session = config.get("max_setups_per_session", 6)
        self.min_signal_spacing_minutes = config.get("min_signal_spacing_minutes", 8)

        self.instrument_params: Dict[str, Dict[str, Any]] = {}
        for instrument in self.instruments:
            overrides = dict(config.get("instrument_params", {}).get(instrument, {}))
            overrides.setdefault("enabled", True)
            overrides.setdefault("target_rr", self.base_rr)
            overrides["target_rr"] = max(2.0, float(overrides["target_rr"]))
            overrides.setdefault("stop_atr", self.base_stop_atr)
            overrides.setdefault("base_confidence", self.min_confidence)
            overrides.setdefault("session", "london")
            self.instrument_params[instrument] = overrides

        session_config = config.get("session_windows", {})
        if not session_config:
            session_config = self.DEFAULT_SESSIONS

        self.session_windows: Dict[str, tuple[time, time]] = {}
        for session_name, window in session_config.items():
            if not isinstance(window, (list, tuple)) or len(window) != 2:
                raise ValueError(f"Invalid session window for {session_name}: {window}")
            start, end = window
            self.session_windows[session_name.lower()] = (_parse_time(start), _parse_time(end))

        self._session_counts: Dict[str, int] = defaultdict(int)
        self._session_dates: Dict[str, datetime.date] = {}
        self._recent_signal_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))

        logger.info("✅ Session Scalper initialized")
        logger.info("   Instruments: %s", ", ".join(self.instruments))
        logger.info("   Sessions: %s", ", ".join(self.session_windows.keys()))

    def analyze(self, market_data) -> List[TradeSignal]:
        signals: List[TradeSignal] = []

        if not self.enabled or not self.instruments:
            return signals

        required_methods = ("get_close_prices", "get_price_history", "get_current_price", "calculate_atr")
        if not all(hasattr(market_data, method) for method in required_methods):
            logger.warning("⚠️ Market data feed missing required methods for Session Scalper")
            return signals

        now = datetime.utcnow()
        current_session = self._detect_session(now.time())
        if not current_session:
            return signals

        self._reset_session_counts_if_needed(current_session, now.date())

        if self._session_counts[current_session] >= self.max_setups_per_session:
            logger.debug("Session %s cap reached (%d)", current_session, self.max_setups_per_session)
            return signals

        for instrument in self.instruments:
            params = self.instrument_params.get(instrument, {})
            if not params.get("enabled", True):
                continue

            session_override = params.get("session", current_session).lower()
            if session_override != current_session:
                continue

            signal = self._generate_signal_for_instrument(
                instrument=instrument,
                market_data=market_data,
                now=now,
                params=params,
            )
            if signal:
                signals.append(signal)
                self._session_counts[current_session] += 1
                if self._session_counts[current_session] >= self.max_setups_per_session:
                    break

        return signals

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _reset_session_counts_if_needed(self, session_name: str, today) -> None:
        last_date = self._session_dates.get(session_name)
        if last_date != today:
            self._session_counts[session_name] = 0
            self._session_dates[session_name] = today

    def _detect_session(self, current_time: time) -> Optional[str]:
        for session_name, (start, end) in self.session_windows.items():
            if start <= current_time <= end:
                return session_name
        return None

    def _generate_signal_for_instrument(
        self,
        instrument: str,
        market_data,
        now: datetime,
        params: Mapping[str, Any],
    ) -> Optional[TradeSignal]:
        close_prices = market_data.get_close_prices(instrument, self.lookback_bars)
        if not close_prices or len(close_prices) < max(self.trend_period_slow * 3, self.lookback_bars // 2):
            return None

        atr = market_data.calculate_atr(instrument, period=14)
        if not atr or atr <= 0:
            return None

        price_info = market_data.get_current_price(instrument)
        if not price_info:
            return None
        mid_price = (price_info.bid + price_info.ask) / 2

        fast_ema = self._ema(close_prices, self.trend_period_fast)
        slow_ema = self._ema(close_prices, self.trend_period_slow)
        if fast_ema is None or slow_ema is None:
            return None

        momentum = (fast_ema - slow_ema) / atr
        direction = "BUY" if momentum > self.momentum_threshold else "SELL" if momentum < -self.momentum_threshold else None
        if direction is None:
            return None

        recent_high = max(close_prices[-self.trend_period_slow :])
        recent_low = min(close_prices[-self.trend_period_slow :])

        pullback = None
        if direction == "BUY":
            pullback = (recent_high - mid_price) / atr
            if not (self.pullback_atr_min <= pullback <= self.pullback_atr_max):
                return None
            entry_price = price_info.ask
            stop_loss = entry_price - atr * params.get("stop_atr", self.base_stop_atr)
            take_profit = entry_price + (entry_price - stop_loss) * params.get("target_rr", self.base_rr)
        else:
            pullback = (mid_price - recent_low) / atr
            if not (self.pullback_atr_min <= pullback <= self.pullback_atr_max):
                return None
            entry_price = price_info.bid
            stop_loss = entry_price + atr * params.get("stop_atr", self.base_stop_atr)
            take_profit = entry_price - (stop_loss - entry_price) * params.get("target_rr", self.base_rr)

        if take_profit is None or stop_loss is None:
            return None

        rr = abs(take_profit - entry_price) / max(1e-9, abs(entry_price - stop_loss))
        if rr < 2.0:
            logger.debug("Discarding %s signal: RR %.2f below 2.0", instrument, rr)
            return None

        if not self._can_emit_signal(instrument, now):
            return None

        confidence = self._compute_confidence(momentum=momentum, pullback=pullback, base=params.get("base_confidence", self.min_confidence))
        confidence = max(self.min_confidence, min(confidence, self.max_confidence))

        signal = TradeSignal(
            instrument=instrument,
            side=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            strategy_name=self.name,
            timestamp=now,
        )

        logger.info(
            "📊 Session Scalper %s signal: %s momentum=%.3f pullback=%.2f ATR=%.3f RR=%.2f conf=%.2f",
            instrument,
            direction,
            momentum,
            pullback if pullback is not None else float("nan"),
            atr,
            rr,
            confidence,
        )

        self._recent_signal_times[instrument].append(now)
        return signal

    def _can_emit_signal(self, instrument: str, now: datetime) -> bool:
        history = self._recent_signal_times[instrument]
        if history:
            delta = (now - history[-1]).total_seconds() / 60
            if delta < self.min_signal_spacing_minutes:
                return False
        return True

    @staticmethod
    def _ema(values: List[float], period: int) -> Optional[float]:
        if not values or len(values) < period:
            return None
        alpha = 2.0 / (period + 1)
        ema = values[0]
        for price in values[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema

    def _compute_confidence(self, momentum: float, pullback: float, base: float) -> float:
        momentum_score = min(abs(momentum) * 1.5, 0.25)
        pullback_score = min(abs(pullback) * 0.2, 0.15)
        return base + momentum_score + pullback_score
