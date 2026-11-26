"""Dated output paths and retained pre-rename reductions."""
import pytest

from efospec.paths import efospec_root, efosc_root, saved_efospec_root


def test_new_outputs_use_efospec_even_when_old_folder_exists(tmp_path):
    old = tmp_path/'runs/2026-10-28/efosc'
    old.mkdir(parents=True)
    expected = old.with_name('efospec')
    assert efospec_root(tmp_path, '2026-10-28') == expected
    assert efosc_root(tmp_path, '2026-10-28') == expected
    with pytest.raises(ValueError):
        efospec_root(tmp_path, '../2026-10-28')


@pytest.mark.parametrize('folder', ['efospec', 'efosc', ''])
def test_explicit_saved_runs_keep_their_layout(tmp_path, folder):
    root = tmp_path/'runs/2026-10-28'/folder
    assert saved_efospec_root(root/'nightly/revision/reduction') == root
    with pytest.raises(ValueError, match='IRAF'):
        saved_efospec_root(tmp_path/'runs/2026-10-28/pessto/iraf-full-01')


def test_compatibility_link_resolves_to_canonical_root(tmp_path):
    root = efospec_root(tmp_path, '2026-10-28')
    root.mkdir(parents=True)
    old = root.with_name('efosc')
    old.symlink_to('efospec', target_is_directory=True)
    assert saved_efospec_root(old/'nightly/revision/reduction') == root
