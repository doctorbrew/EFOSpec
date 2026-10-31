"""Compatibility alias for efospec.naming."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.naming")
