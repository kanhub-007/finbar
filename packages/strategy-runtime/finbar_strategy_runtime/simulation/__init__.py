"""Simulation primitives — sizing, fill model, metrics (Layer B).

These are pure deterministic services. No loop, no runner, no venue.
Finbar's BacktestRunner imports these primitives; finbot's fake exchange
composes them for dry-run/replay.
"""
