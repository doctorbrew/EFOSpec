"""Compatibility alias for efospec.download."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.download")
