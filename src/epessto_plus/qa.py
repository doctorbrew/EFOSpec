"""Compatibility alias for efospec.qa."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.qa")
