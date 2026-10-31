"""Compatibility alias for efospec.spatial_profiles."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.spatial_profiles")
