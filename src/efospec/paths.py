"""Shared output locations for the two reduction engines."""
from datetime import date
from pathlib import Path


def efosc_root(project, night):
    if date.fromisoformat(night).isoformat() != night:
        raise ValueError('observing date must be YYYY-MM-DD')
    return Path(project).resolve() / 'runs' / night / 'efosc'


def dated_root(path):
    """Find the dated container without assuming a fixed revision depth."""
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if parent.parent.name == 'runs':
            try:
                if date.fromisoformat(parent.name).isoformat() == parent.name:
                    return parent
            except ValueError:
                pass
    raise ValueError(f'Not inside a dated runs directory: {path}')


def saved_efosc_root(path):
    """Resolve new EFOSpec runs and explicitly opened historical runs."""
    path = Path(path).resolve()
    dated = dated_root(path)
    if path.is_relative_to(dated / 'efosc'):
        return dated / 'efosc'
    if path.is_relative_to(dated / 'pessto'):
        raise ValueError('An IRAF output directory is not an EFOSpec run')
    return dated
