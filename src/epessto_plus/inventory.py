"""Compatibility alias for efospec.inventory."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.inventory")
