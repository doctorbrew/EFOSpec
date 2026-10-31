"""Compatibility alias for efospec.report."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.report")
