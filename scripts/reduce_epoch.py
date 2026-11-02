#!/usr/bin/env python3
"""Run one dated EFOSpec workflow stage; use the project Python environment."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from efospec.nightly import script_main

if __name__=='__main__':
    raise SystemExit(script_main('all'))
