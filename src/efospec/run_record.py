"""Freeze the Python source used for an experimental reduction or revision."""
from pathlib import Path
import shutil
from .inventory import sha256


def snapshot_sources(output):
    destination=Path(output)/'source';destination.mkdir(parents=True,exist_ok=False)
    hashes={}
    for path in sorted(Path(__file__).parent.glob('*.py')):
        shutil.copyfile(path,destination/path.name);hashes[path.name]=sha256(path)
    return hashes
