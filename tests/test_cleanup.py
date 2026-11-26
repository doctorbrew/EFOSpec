"""A reset is date-scoped, reversible and never follows output symlinks."""
import json
import os
from pathlib import Path

import pytest

from efospec.cleanup import cleanup_night, script_main
from efospec.__main__ import main


@pytest.fixture
def project(tmp_path):
    for name in ('data/2026-10-28/raw.fits', 'runs/2026-10-28/pessto/science.fits',
                 'runs/2026-10-29/efospec/nightly/accepted.fits',
                 'runs/2026-10-28/efospec/nightly/broken/run.json',
                 'runs/2026-10-28/efospec/calibrations/arc.fits',
                 'runs/2026-10-28/efospec/delivery/spectrum.fits'):
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'original bytes: '+name.encode())
    (tmp_path/'runs/2026-10-28/efosc').symlink_to('efospec', target_is_directory=True)
    return tmp_path


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_preview_and_apply_preserve_bytes_and_other_engines(project):
    before = snapshot(project)
    preview = cleanup_night('2026-10-28', project)
    assert preview['status'] == 'dry_run'
    assert snapshot(project) == before
    assert not (project/'runs/2026-10-28/archive').exists()
    source = Path(preview['source'])
    products = snapshot(source)
    # An internal link is moved as a link, never traversed to remove raw data.
    (source/'raw-link').symlink_to(project/'data')
    result = cleanup_night('2026-10-28', project, apply=True)
    backup = Path(result['destination'])
    assert not source.exists()
    assert backup.joinpath('raw-link').is_symlink()
    assert snapshot(backup) == products
    assert all((project/name).read_bytes() == content for name, content in before.items()
               if not name.startswith('runs/2026-10-28/efospec/'))
    assert json.loads((backup.parent/'cleanup.json').read_text())['status'] == 'archived'
    assert cleanup_night('2026-10-28', project, apply=True)['status'] == 'nothing_to_clean'
    # Restore without rewriting saved manifests or products.
    backup.rename(source)
    assert snapshot(source) == products
    assert source.with_name('efosc').resolve() == source


@pytest.mark.parametrize('night', ['../2026-10-28', '2026-1-2', '2026-02-30', '*'])
def test_rejects_non_dates(project, night):
    before = snapshot(project)
    with pytest.raises(ValueError):cleanup_night(night, project, apply=True)
    assert snapshot(project) == before


@pytest.mark.parametrize('location', ['runs', 'runs/2026-10-28',
    'runs/2026-10-28/efospec', 'runs/2026-10-28/archive'])
def test_rejects_symlinked_output_containers(tmp_path, location):
    outside = tmp_path/'raw';outside.mkdir();(outside/'keep.fits').write_bytes(b'raw')
    link = tmp_path/location;link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    if location.endswith('archive'):
        (link.parent/'efospec').mkdir()
    with pytest.raises(ValueError, match='symlink'):cleanup_night('2026-10-28', tmp_path, apply=True)
    assert (outside/'keep.fits').read_bytes() == b'raw'


def test_running_and_stale_locks(project, monkeypatch):
    lock = project/'runs/2026-10-28/efospec/nightly/.running'
    lock.write_text(str(os.getpid()))
    with pytest.raises(ValueError, match='lock exists'):cleanup_night('2026-10-28', project, apply=True)
    with pytest.raises(ValueError, match='still running'):
        cleanup_night('2026-10-28', project, apply=True, clear_stale_lock=True)
    def dead(pid, signal):raise ProcessLookupError
    monkeypatch.setattr('efospec.cleanup.os.kill', dead)
    cleanup_night('2026-10-28', project, clear_stale_lock=True)
    assert lock.exists()  # Preview must not remove a stale lock.
    result = cleanup_night('2026-10-28', project, apply=True, clear_stale_lock=True)
    assert not (Path(result['destination'])/'nightly/.running').exists()
    assert not (project/'runs/2026-10-28/.cleanup-running').exists()


def test_failed_move_releases_own_locks_and_preserves_outputs(project, monkeypatch):
    before = snapshot(project)
    def fail(*args):raise OSError('simulated rename failure')
    monkeypatch.setattr(Path, 'rename', fail)
    with pytest.raises(OSError, match='simulated'):
        cleanup_night('2026-10-28', project, apply=True)
    assert all((project/name).read_bytes() == content for name, content in before.items())
    assert not (project/'runs/2026-10-28/.cleanup-running').exists()
    assert not (project/'runs/2026-10-28/efospec/nightly/.running').exists()


def test_both_entry_points_default_to_preview(project, capsys):
    args = ['2026-10-28', '--project-root', str(project)]
    assert script_main(args) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'dry_run'
    assert main(['cleanup-night', *args]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'dry_run'
