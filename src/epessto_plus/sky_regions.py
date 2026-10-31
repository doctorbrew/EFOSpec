"""Compatibility alias for efospec.sky_regions."""
import importlib
import sys

if __name__ == "__main__":
    from efospec.sky_regions import main
    main()
else:
    sys.modules[__name__] = importlib.import_module("efospec.sky_regions")
