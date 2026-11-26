"""Retire one night's PypeIt output tree without deleting scientific files."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from .paths import efospec_root


def cleanup_night(night, project_root='.', *, apply=False, clear_stale_lock=False):
    root = efospec_root(project_root, night)
    # Never follow output/container links into raw data or another night.
    for path in (root.parent.parent, root.parent, root):
        if path.is_symlink():
            raise ValueError(f'Refusing symlinked output location: {path}')
    legacy = root.with_name('efosc')
    if legacy.exists() or legacy.is_symlink():
        if not legacy.is_symlink() or legacy.resolve() != root:
            raise ValueError(f'Legacy output must first be migrated to efospec: {legacy}')
    result = dict(night=night, source=str(root), status='nothing_to_clean')
    if not root.exists():
        return result
    if not root.is_dir():
        raise ValueError(f'Output location is not a directory: {root}')
    archive = root.parent/'archive'
    if archive.is_symlink():
        raise ValueError(f'Refusing symlinked archive: {archive}')
    token = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    destination = archive/('cleanup-'+token)/'efospec'
    lock = root/'nightly/.running'
    pid = None
    if (root/'nightly').is_symlink():
        raise ValueError('Refusing symlinked nightly directory')
    if lock.exists() or lock.is_symlink():
        if not clear_stale_lock:
            raise ValueError(f'Nightly lock exists: {lock}; stop workers first. '
                             'Use --clear-stale-lock only for a dead process.')
        if lock.is_symlink():
            raise ValueError('Refusing symlinked nightly lock')
        try:
            pid = int(lock.read_text().strip())
            if pid <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(f'Invalid PID in {lock}; inspect the lock manually') from None
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        except PermissionError:
            raise ValueError(f'Process {pid} may still be running') from None
        else:
            raise ValueError(f'Process {pid} is still running; cleanup refused')
    result.update(status='dry_run', destination=str(destination),
                  scope='Entire PypeIt output tree, including calibrations, QC, reports and delivery copies')
    if not apply:
        return result
    # Serialize cleanup invocations; the nightly lock also prevents a new stage.
    guard = root.parent/'.cleanup-running'
    try:
        handle = guard.open('x')
    except FileExistsError:
        raise ValueError(f'Cleanup lock exists: {guard}') from None
    acquired = False
    moved = False
    archive_created = False
    try:
        with handle:
            handle.write(f'{os.getpid()}\n')
        if not root.is_dir() or root.is_symlink():
            raise ValueError('Output directory changed during cleanup')
        if pid is not None and lock.exists():
            # Do not remove a newly acquired lock in place of the inspected one.
            if lock.read_text().strip() != str(pid):
                raise ValueError('Nightly lock changed during cleanup')
            lock.unlink()
        lock.parent.mkdir(exist_ok=True)
        with lock.open('x') as stream:
            stream.write(f'{os.getpid()}\n')
        acquired = True
        destination.parent.mkdir(parents=True, exist_ok=False)
        archive_created = True
        record = dict(result, status='archived',
                      note='Restore efospec to its original location before using saved absolute-path manifests.')
        (destination.parent/'cleanup.json').write_text(json.dumps(record, indent=2)+'\n')
        root.rename(destination)
        moved = True
        return record
    except BaseException:
        if archive_created and not moved:
            (destination.parent/'cleanup.json').unlink(missing_ok=True)
            destination.parent.rmdir()
        raise
    finally:
        if acquired:
            held_lock = destination/'nightly/.running' if moved else lock
            held_lock.unlink()
        guard.unlink()


def add_arguments(parser):
    parser.add_argument('night', help='One observing night, YYYY-MM-DD')
    parser.add_argument('--project-root', default='.', help='EFOSpec directory containing runs/ and data/')
    parser.add_argument('--apply', action='store_true', help='Move outputs to dated archive; default is dry run')
    parser.add_argument('--clear-stale-lock', action='store_true', help='Clear nightly lock only if its PID no longer exists')


def run(args):
    result = cleanup_night(args.night, args.project_root, apply=args.apply,
                           clear_stale_lock=args.clear_stale_lock)
    print(json.dumps(result, indent=2))
    return 0


def script_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'cleanup-night: {exc}\n')
