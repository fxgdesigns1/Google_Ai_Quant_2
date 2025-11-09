from pathlib import Path

from analysis.session_scalper_optimizer import (
    classify_instruments,
    generate_focused_sweep,
    identify_top_sets,
    load_results,
    monte_carlo_resample,
)


def _sample_results_path() -> Path:
    root = Path(__file__).parent.parent
    return root / "data" / "backtests" / "session_scalper_results.sample.json"


def test_classification_detects_promoted_pairs():
    runs = load_results(_sample_results_path())
    best = identify_top_sets(runs, min_profit_factor=1.0)
    classifications = classify_instruments(best, marginal_threshold=0.1)
    assert classifications["XAU_USD"] == "promote"
    assert classifications["USD_CAD"] == "promote"


def test_generate_focused_sweep_includes_base_params():
    runs = load_results(_sample_results_path())
    best = identify_top_sets(runs, min_profit_factor=1.0)
    sweep = generate_focused_sweep(best["XAU_USD"], steps=1)
    base_params = best["XAU_USD"].parameters
    assert any(candidate == base_params for candidate in sweep)


def test_monte_carlo_resample_returns_expected_keys():
    runs = load_results(_sample_results_path())
    best = identify_top_sets(runs, min_profit_factor=1.0)
    summary = monte_carlo_resample(best["XAU_USD"].trades, iterations=20, sample_size=2, seed=42)
    for key in {"mean_return", "median_return", "p05_return", "p95_return"}:
        assert key in summary
