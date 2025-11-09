#!/usr/bin/env python3
"""
Session Scalper Optimizer
=========================

Utility helpers for analysing Session Scalper backtest output, promoting
profitable parameter sets, designing focused sweep grids, and running
Monte Carlo resampling on per-trade results.

Expected JSON structure (flexible):
{
  "pairs": {
     "XAU_USD": [
        {
           "id": "xau_run_001",
           "parameters": {"stop_atr": 1.8, "risk_reward": 2.2, ...},
           "metrics": {"net_profit": 1050.0, "max_drawdown": -3.5, ...},
           "trades": [
              {"pnl": 150.0, "rr": 2.4, "date": "2025-10-07T14:30:00Z"},
              ...
           ]
        },
        ...
     ],
     "USD_CAD": [...]
  }
}

Alternative layouts are supported:
 - A list of parameter set dictionaries with an "instrument" field
 - Nested dicts keyed by instrument then by run id

Usage (CLI):
    python analysis/session_scalper_optimizer.py summary
    python analysis/session_scalper_optimizer.py sweep --pair XAU_USD
    python analysis/session_scalper_optimizer.py monte-carlo --pair USD_CAD
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


DEFAULT_RESULTS_PATH = Path("data/backtests/session_scalper_results.json")


@dataclass
class TradeRecord:
    """Single trade outcome used for Monte Carlo resampling."""

    pnl: float
    rr: Optional[float] = None
    timestamp: Optional[str] = None


@dataclass
class ParameterSet:
    """Container for a single sweep/backtest run."""

    run_id: str
    instrument: str
    parameters: Dict[str, Any]
    metrics: Dict[str, Any]
    trades: List[TradeRecord] = field(default_factory=list)

    def net_profit(self) -> float:
        return float(self.metrics.get("net_profit", 0.0))

    def profit_factor(self) -> float:
        return float(self.metrics.get("profit_factor", 0.0))

    def max_drawdown(self) -> float:
        return float(self.metrics.get("max_drawdown", 0.0))

    def total_trades(self) -> int:
        value = self.metrics.get("total_trades")
        if value is not None:
            return int(value)
        return len(self.trades)

    def expectancy(self) -> Optional[float]:
        return self.metrics.get("expectancy")


def _flatten_results(data: Any) -> List[ParameterSet]:
    """
    Normalize heterogeneous JSON layouts into a list of ParameterSet objects.
    """
    results: List[ParameterSet] = []

    if isinstance(data, Mapping):
        # Common layout: {"pairs": {"XAU_USD": [ ... ]}}
        if "pairs" in data and isinstance(data["pairs"], Mapping):
            for instrument, runs in data["pairs"].items():
                results.extend(_parse_runs(runs, instrument))
        else:
            # Maybe instrument keyed dict directly
            for instrument, runs in data.items():
                results.extend(_parse_runs(runs, instrument))
    elif isinstance(data, Sequence):
        for entry in data:
            if isinstance(entry, Mapping):
                instrument = entry.get("instrument", "UNKNOWN")
                results.extend(_parse_runs([entry], instrument))
    else:
        raise ValueError("Unsupported session scalper JSON structure")

    return results


def _parse_runs(runs: Any, instrument_hint: str) -> List[ParameterSet]:
    parsed: List[ParameterSet] = []

    if isinstance(runs, Mapping):
        # Could be dict keyed by run id
        for run_id, payload in runs.items():
            if isinstance(payload, Mapping):
                parsed.append(_build_param_set(payload, instrument_hint, run_id=run_id))
    elif isinstance(runs, Sequence):
        for payload in runs:
            if isinstance(payload, Mapping):
                parsed.append(_build_param_set(payload, instrument_hint))
    else:
        raise ValueError(f"Unsupported runs layout for {instrument_hint}")

    return parsed


def _build_param_set(payload: Mapping[str, Any], instrument_hint: str, run_id: Optional[str] = None) -> ParameterSet:
    instrument = str(payload.get("instrument", instrument_hint))
    parameters = dict(payload.get("parameters", {}))
    metrics = dict(payload.get("metrics", {}))
    trades_payload = payload.get("trades", [])

    trades: List[TradeRecord] = []
    if isinstance(trades_payload, Sequence):
        for trade in trades_payload:
            if not isinstance(trade, Mapping):
                continue
            pnl = float(trade.get("pnl", trade.get("profit", 0.0)))
            rr = trade.get("rr") or trade.get("rr_ratio") or trade.get("risk_reward")
            timestamp = trade.get("timestamp") or trade.get("time") or trade.get("date")
            trades.append(TradeRecord(pnl=pnl, rr=float(rr) if rr is not None else None, timestamp=timestamp))

    identifier = run_id or str(payload.get("id") or payload.get("run_id") or f"{instrument}_{len(trades)}")

    return ParameterSet(
        run_id=identifier,
        instrument=instrument,
        parameters=parameters,
        metrics=metrics,
        trades=trades,
    )


def load_results(path: Path = DEFAULT_RESULTS_PATH) -> List[ParameterSet]:
    """Load and parse Session Scalper backtest output."""
    if not path.exists():
        raise FileNotFoundError(f"Session Scalper results file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    return _flatten_results(data)


def identify_top_sets(
    runs: Sequence[ParameterSet],
    min_profit_factor: float = 1.3,
    min_net_profit: float = 0.0,
) -> Dict[str, ParameterSet]:
    """
    Pick the best run per instrument using net profit, profit factor and drawdown filters.
    """
    best: Dict[str, ParameterSet] = {}

    for run in runs:
        if run.profit_factor() < min_profit_factor:
            continue
        if run.net_profit() < min_net_profit:
            continue

        current_best = best.get(run.instrument)
        if current_best is None:
            best[run.instrument] = run
            continue

        # Prefer higher profit, then lower drawdown, then higher expectancy
        if run.net_profit() > current_best.net_profit():
            best[run.instrument] = run
        elif math.isclose(run.net_profit(), current_best.net_profit(), rel_tol=1e-4):
            if run.max_drawdown() < current_best.max_drawdown():
                best[run.instrument] = run
            elif math.isclose(run.max_drawdown(), current_best.max_drawdown(), rel_tol=1e-4):
                if (run.expectancy() or 0) > (current_best.expectancy() or 0):
                    best[run.instrument] = run

    return best


def classify_instruments(best_runs: Mapping[str, ParameterSet], marginal_threshold: float = 0.5) -> Dict[str, str]:
    """
    Categorise instruments into promote/marginal/disable buckets.
    """
    classifications: Dict[str, str] = {}
    for instrument, run in best_runs.items():
        net = run.net_profit()
        profit_factor = run.profit_factor()
        total_trades = run.total_trades()

        if net <= 0 or profit_factor < 1.2:
            classifications[instrument] = "disable"
        elif net < marginal_threshold * abs(run.max_drawdown()):
            classifications[instrument] = "marginal"
        elif total_trades < 15:
            classifications[instrument] = "marginal"
        else:
            classifications[instrument] = "promote"
    return classifications


def generate_focused_sweep(
    run: ParameterSet,
    stop_variation: float = 0.15,
    rr_variation: float = 0.2,
    steps: int = 3,
) -> List[Dict[str, Any]]:
    """
    Construct a tightened parameter grid around the winning set.
    """
    base_params = run.parameters
    sweep: List[Dict[str, Any]] = []

    for step in range(-steps, steps + 1):
        if step == 0:
            sweep.append(dict(base_params))
            continue

        candidate = dict(base_params)
        factor = 1.0 + (stop_variation * step / steps)
        rr_factor = 1.0 + (rr_variation * step / steps)

        for key, value in base_params.items():
            if isinstance(value, (int, float)):
                lower_key = key.lower()
                if "stop" in lower_key or "atr" in lower_key:
                    candidate[key] = round(float(value) * factor, 5)
                elif "rr" in lower_key or "reward" in lower_key:
                    adjusted = max(2.0, float(value) * rr_factor)
                    candidate[key] = round(adjusted, 3)
                elif "position" in lower_key and "multiplier" in lower_key:
                    candidate[key] = round(min(float(value) * factor, 1.25), 4)
                elif "session_offset" in lower_key:
                    candidate[key] = int(round(float(value) + step))
            elif isinstance(value, Mapping):
                candidate[key] = _adjust_nested_params(value, factor, rr_factor)

        sweep.append(candidate)

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for candidate in sweep:
        frozen = json.dumps(candidate, sort_keys=True)
        if frozen not in seen:
            seen.add(frozen)
            deduped.append(candidate)

    return deduped


def _adjust_nested_params(value: Mapping[str, Any], factor: float, rr_factor: float) -> Dict[str, Any]:
    nested = dict(value)
    for n_key, n_val in value.items():
        if isinstance(n_val, (int, float)):
            lower = n_key.lower()
            if "stop" in lower or "atr" in lower:
                nested[n_key] = round(float(n_val) * factor, 5)
            elif "rr" in lower or "reward" in lower:
                nested[n_key] = round(max(2.0, float(n_val) * rr_factor), 3)
            elif "size" in lower or "multiplier" in lower:
                nested[n_key] = round(min(float(n_val) * factor, 1.25), 4)
        elif isinstance(n_val, Mapping):
            nested[n_key] = _adjust_nested_params(n_val, factor, rr_factor)
    return nested


def monte_carlo_resample(
    trades: Sequence[TradeRecord],
    iterations: int = 2000,
    sample_size: Optional[int] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run bootstrap resampling on trade list and compute distribution metrics.
    """
    if not trades:
        raise ValueError("No trades available for Monte Carlo resampling.")

    if seed is not None:
        random.seed(seed)

    sample_size = sample_size or len(trades)
    pnls = [trade.pnl for trade in trades]
    rr_values = [trade.rr for trade in trades if trade.rr is not None]

    equity_paths: List[List[float]] = []
    total_returns: List[float] = []

    for _ in range(iterations):
        sample = [random.choice(pnls) for _ in range(sample_size)]
        equity_curve = _equity_curve(sample)
        equity_paths.append(equity_curve)
        total_returns.append(equity_curve[-1])

    max_drawdowns = [_max_drawdown(path) for path in equity_paths]

    summary = {
        "iterations": iterations,
        "sample_size": sample_size,
        "mean_return": statistics.mean(total_returns),
        "median_return": statistics.median(total_returns),
        "p05_return": statistics.quantiles(total_returns, n=20)[0],  # 5th percentile
        "p95_return": statistics.quantiles(total_returns, n=20)[-1],  # 95th percentile
        "mean_max_drawdown": statistics.mean(max_drawdowns),
        "median_max_drawdown": statistics.median(max_drawdowns),
        "p95_drawdown": statistics.quantiles(max_drawdowns, n=20)[-1],
        "rr_distribution": _describe_rr(rr_values) if rr_values else None,
    }

    return summary


def _equity_curve(sample: Sequence[float]) -> List[float]:
    curve = [0.0]
    for pnl in sample:
        curve.append(curve[-1] + pnl)
    return curve


def _max_drawdown(curve: Sequence[float]) -> float:
    peak = curve[0]
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        drawdown = peak - value
        max_dd = max(max_dd, drawdown)
    return max_dd


def _describe_rr(rr_values: Sequence[float]) -> Optional[Dict[str, float]]:
    if not rr_values:
        return None
    return {
        "mean": statistics.mean(rr_values),
        "median": statistics.median(rr_values),
        "min": min(rr_values),
        "max": max(rr_values),
        "p25": statistics.quantiles(rr_values, n=4)[0],
        "p75": statistics.quantiles(rr_values, n=4)[-1],
    }


def summarise(results_path: Path = DEFAULT_RESULTS_PATH) -> Dict[str, Any]:
    """Generate a high-level summary of the current results file."""
    runs = load_results(results_path)
    best = identify_top_sets(runs)
    classifications = classify_instruments(best)

    summary = {}
    for instrument, run in best.items():
        summary[instrument] = {
            "classification": classifications[instrument],
            "run_id": run.run_id,
            "net_profit": run.net_profit(),
            "profit_factor": run.profit_factor(),
            "max_drawdown": run.max_drawdown(),
            "total_trades": run.total_trades(),
        }
    return summary


def _cli_summary(args: argparse.Namespace) -> None:
    summary = summarise(Path(args.results))
    for instrument, payload in summary.items():
        print(f"{instrument}: {payload['classification'].upper()} (run {payload['run_id']})")
        print(
            f"  net={payload['net_profit']:.2f} | PF={payload['profit_factor']:.2f} | "
            f"DD={payload['max_drawdown']:.2f} | trades={payload['total_trades']}"
        )


def _cli_sweep(args: argparse.Namespace) -> None:
    runs = load_results(Path(args.results))
    best = identify_top_sets(runs)

    instrument = args.pair
    if instrument not in best:
        raise SystemExit(f"No profitable run found for {instrument}")

    sweep = generate_focused_sweep(best[instrument])
    print(json.dumps({"instrument": instrument, "focused_grid": sweep}, indent=2))


def _cli_monte_carlo(args: argparse.Namespace) -> None:
    runs = load_results(Path(args.results))
    best = identify_top_sets(runs)

    instrument = args.pair
    if instrument not in best:
        raise SystemExit(f"No profitable run found for {instrument}")

    summary = monte_carlo_resample(
        best[instrument].trades,
        iterations=args.iterations,
        sample_size=args.sample_size,
        seed=args.seed,
    )
    print(json.dumps({"instrument": instrument, "monte_carlo": summary}, indent=2))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Session Scalper optimizer utilities.")
    parser.add_argument(
        "--results",
        default=str(DEFAULT_RESULTS_PATH),
        help="Path to session scalper results JSON (default: data/backtests/session_scalper_results.json)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    summary_parser = subparsers.add_parser("summary", help="Print classification summary.")
    summary_parser.set_defaults(func=_cli_summary)

    sweep_parser = subparsers.add_parser("sweep", help="Generate a focused parameter grid for a pair.")
    sweep_parser.add_argument("--pair", required=True, help="Instrument symbol (e.g., XAU_USD).")
    sweep_parser.set_defaults(func=_cli_sweep)

    mc_parser = subparsers.add_parser("monte-carlo", help="Run Monte Carlo resampling for a pair.")
    mc_parser.add_argument("--pair", required=True, help="Instrument symbol (e.g., USD_CAD).")
    mc_parser.add_argument("--iterations", type=int, default=2000, help="Bootstrap iterations.")
    mc_parser.add_argument("--sample-size", type=int, default=None, help="Sample size per bootstrap iteration.")
    mc_parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    mc_parser.set_defaults(func=_cli_monte_carlo)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
