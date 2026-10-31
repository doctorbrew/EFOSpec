"""Resolve delivered run files without changing historical manifest records."""
from pathlib import Path


def resolve_result_paths(result, run_directory):
    """Return a copy bound to this run's products, never an old checkout's copy."""
    run = Path(run_directory).resolve()
    resolved = dict(result)
    for key, directory in (('product', 'products'), ('native_spec1d', 'native')):
        if key not in result:
            continue
        path = run/directory/Path(result[key]).name
        if not path.is_file():
            raise FileNotFoundError(f'Missing {key} in selected run: {path}')
        resolved[key] = str(path)
    return resolved
