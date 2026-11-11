# Working on EFOSpec

## Set up

Use the installation commands in the [README](../README.md) and activate the
`efospec` environment. Run commands from the checkout. The tested runtime is
Python 3.11 with PypeIt 3.0.0. Figures require LaTeX and the project plotting
extras; the desktop uses PySide6. The package metadata's broader Python floor is
not a claim that other versions passed the scientific acceptance runs.

For test dependencies and platform-specific configuration, follow [CI](ci.md).
A focused check in the configured environment is:

```sh
MPLBACKEND=Agg python -m pytest tests/test_nightly.py tests/test_epoch_report.py -q
python -m efospec --help
git diff --check
```

Use `MPLBACKEND=Agg python -m pytest tests -q` for a broad run when warranted.
Desktop interaction tests need the display environment documented in the CI guide.
A test pass does not establish astrophysical identity or scientific acceptance.

## Find the right code

| Work | Modules / entry points |
| --- | --- |
| CLI and date orchestration | `__main__.py`, `nightly.py`, `scripts/reduce_epoch.py` |
| Raw inventory and download | `inventory.py`, `download.py` |
| Native calibration and same-night reductions | `native_calibrations.py`, `native_reduction.py`, `daily_reduction.py` |
| Extraction and local sky | `extraction.py`, `local_sky.py`, `products.py` |
| GUI and saved recipes | `desktop.py`, `desktop_session.py`, `recipes.py`, `revisions.py` |
| Nightly HTML and figure displays | `epoch_report.py`, `report.py`, `scripts/preview_spectrum_style.py` |
| Optional historical IRAF comparison | `iraf_comparison.py`, `iraf_report.py` |
| Acquisition targets and catalogues | `acquisition_target.py`, `catalogue_plots.py`, `recovery_qc.py` |

Module names in this table are under `src/efospec/` unless a path is shown.

## Change and verify

- Read `AGENTS.md` and the relevant workflow/validation document before editing.
- Keep display-only work separate from extraction, calibration, masks and thresholds.
- Preserve raw FITS, accepted products, saved recipes and previous processing revisions.
  Run one explicitly named observing date at a time.
- Use `plot_style.py` and `figure_style.py` for scientific plots. Keep PDF and
  300-dpi JPG exports, LaTeX, units and recorded input hashes.
- Run focused behavior checks for substantive changes, inspect regenerated plots,
  and rebuild reports only for the requested dates.
- Record significant maintenance changes in [the development log](DEVELOPMENT_LOG.md).
  Keep current instructions in their topic documents, not in duplicate histories.

## Keep the checkout clean

`data/`, `runs/` and `outputs/` are recursively ignored. Do not force-add science
files or apply a blanket FITS ignore rule: bundled reference calibrations under
`trunk/src/ntt/` must remain versioned. Do not move old run folders solely because
they look stale; manifests and recipes can contain absolute paths into them.

Builds recreate `build/` and `dist/`; CI recreates `badge-data/` and `test-results/`.
These are ignored, disposable working directories. Retained local audit evidence
belongs in `outputs/`; dated science products stay under `runs/DATE/`.
