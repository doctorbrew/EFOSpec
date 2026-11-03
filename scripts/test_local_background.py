#!/usr/bin/env python3
"""Check or extract explicitly named targets in one observing epoch."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from efospec.local_sky_trials import main

if __name__=='__main__':main()
