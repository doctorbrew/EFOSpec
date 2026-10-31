"""Compatibility entry point; prefer python -m efospec."""
from efospec.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
