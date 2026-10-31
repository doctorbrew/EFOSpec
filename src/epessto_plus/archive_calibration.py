"""Compatibility alias for efospec.archive_calibration."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("efospec.archive_calibration")
