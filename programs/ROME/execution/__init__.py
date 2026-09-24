"""ROME execution: brokers, the run loop, costs, state and reporting.

Everything that touches the outside world — orders, disk, the clock — lives
here, so ../strategy/ can stay pure and testable.
"""
