"""Domain services — pure business logic with no I/O dependencies.

Finbar-local services (annualization, backtest_metrics, correlation,
rolling_metrics) live in this directory.

Services shared with finbar_strategy_runtime are imported directly from
``finbar_strategy_runtime.domain.services.*`` — no re-export needed.
"""
