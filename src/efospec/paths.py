"""Shared output locations for the two reduction engines."""
from datetime import date
from pathlib import Path


def efospec_root(project, night):
    if date.fromisoformat(night).isoformat() != night:
        raise ValueError('observing date must be YYYY-MM-DD')
    return Path(project).resolve() / 'runs' / night / 'efospec'


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


def saved_efospec_root(path):
    """Resolve new EFOSpec runs and explicitly opened historical runs."""
    path = Path(path).resolve()
    dated = dated_root(path)
    for name in ('efospec', 'efosc'):
        if path.is_relative_to(dated / name):
            return dated / name
    if path.is_relative_to(dated / 'pessto'):
        raise ValueError('An IRAF output directory is not an EFOSpec run')
    return dated


# Retain imports used by older observer scripts; new output uses efospec.
efosc_root = efospec_root
saved_efosc_root = saved_efospec_root


def file_hashes_match(saved, expected):
    """Compare provenance through compatibility links without rewriting records."""
    return {(Path(p).resolve(), h) for p, h in saved.items()} == {
        (Path(p).resolve(), h) for p, h in expected.items()}
