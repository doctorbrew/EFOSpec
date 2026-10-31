"""Compatibility alias for efospec.native_readiness."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.native_readiness")
