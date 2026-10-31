"""Compatibility alias for efospec.pypeit_adapter."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.pypeit_adapter")
