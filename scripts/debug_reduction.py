"""Run one legacy reduction in a fresh directory of copied inputs and record evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['fast','full2d','full1d'])
    parser.add_argument('--input',action='append',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--iraf-root',default='/usr/local/lib/iraf/')
    parser.add_argument('--timeout',type=int,default=300)
    args=parser.parse_args()
    sources=[p.resolve(strict=True) for p in args.input]
    if len({p.name for p in sources})!=len(sources):
        parser.error('Input basenames must be unique')
    if args.stage=='fast' and len(sources)!=1:
        parser.error('Fast debug runs take exactly one exposure')
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    before={str(p):sha(p) for p in sources}
    for p in sources:shutil.copy2(p,output/p.name)
    (output/'cache').mkdir()
    (output/'inputs.list').write_text(''.join(p.name+'\n' for p in sources))
    executable={'fast':'PESSTOFASTSPEC','full2d':'PESSTOEFOSC2dSPEC','full1d':'PESSTOEFOSC1dSPEC'}[args.stage]
    command=[str(Path(sys.executable).parent/executable),sources[0].name if args.stage=='fast' else 'inputs.list']
    env=dict(os.environ,PYRAF_NO_DISPLAY='1',MPLBACKEND='Agg',PYRAF_CLCACHE_PATH=str(output/'cache'),iraf=str(Path(args.iraf_root).resolve())+'/')
    record=dict(command=command,python=sys.version,machine=platform.machine(),inputs=before,interactive=False)
    with (output/'reduction.log').open('w') as log:
        proc=subprocess.Popen(command,cwd=output,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:record['returncode']=proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            record.update(returncode=proc.returncode,timed_out=True)
    record['raw_inputs_unchanged']=all(sha(p)==before[str(p)] for p in sources)
    record['generated_files']={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file() and p.name not in {x.name for x in sources} and 'cache' not in p.relative_to(output).parts}
    (output/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(output/'reduction.log')
    return 0 if record['returncode']==0 and record['raw_inputs_unchanged'] else 1

if __name__=='__main__':sys.exit(main())
