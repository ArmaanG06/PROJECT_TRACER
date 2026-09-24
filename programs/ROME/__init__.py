"""ROME — ETF pairs trading.

Importable as `ROME` once `pip install -e .` has run, from any directory:

    from ROME.strategy import engine
    from ROME.execution import runner

Config lives in the root configs.yaml under `strategies.ROME`.
Prices come from data/store/ROME.duckdb via `from data_pulling import get_prices`.
"""
