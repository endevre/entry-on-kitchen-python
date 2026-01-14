"""
Entry on Kitchen Python Library

A simple Python library for executing recipes on the Entry on Kitchen API.
Supports both synchronous execution and real-time streaming.
"""

from .Kitchen import KitchenClient

__version__ = "0.3.0"
__all__ = ["KitchenClient"]
