#!/usr/bin/env python3
"""Measure independent spectral candidates and record NED matches for one night."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from efospec.redshift_run import measure_night,activate_measurements

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('night');p.add_argument('--output',required=True)
    p.add_argument('--rescue');p.add_argument('--project-root',default='.')
    p.add_argument('--update-report',action='store_true',help='Activate complete measurements matching current reductions and rebuild the dated report')
    a=p.parse_args();r=measure_night(a.night,a.output,project_root=a.project_root,rescue=a.rescue)
    if a.update_report:print(json.dumps(activate_measurements(a.output,project_root=a.project_root)))
    print(json.dumps(dict(status=r['status'],results=len(r['results']),errors=r['errors'])))
