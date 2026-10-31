"""Compatibility alias for efospec.planning."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.planning")
