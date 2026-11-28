# Repository layout

**`runs/` is the only generated-output root.** Raw inputs remain in `data/`;
source code, documentation and environments are separate from generated results.
The code repository's default branch is `master`.

| Location | Purpose | Git |
| --- | --- | --- |
| `src/efospec/` | Active engine, desktop app and report code | Tracked |
| `src/epessto_plus/` | Compatibility imports for the former package name | Tracked |
| `scripts/`, `configs/`, `tests/` | Workflow entry points, configuration and checks | Tracked |
| `.github/` | Automated builds, tests and badge updates | Tracked |
| `.gitignore` | Excludes local data, products, caches and credentials | Tracked |
| `docs/` | Project documentation; explicit local exclusions apply | Mostly tracked |
| `docs/manual/` | Maintained manual content and figures | Tracked |
| `manual_pessto.html` | Standalone generated manual, an intentional published/package artifact | Tracked |
| `docs/references/pessto/` | External PDF manuals and retained supporting materials | Ignored |
| `trunk/` | Preserved PESSTO engine and reference calibrations | Tracked baseline |
| `data/DATE/` | Original observing inputs and downloaded calibrations | Ignored |
| `data/reference-deliveries/` | Supplied public/private delivery-format examples | Ignored |
| `runs/DATE/efospec/` | Dated reductions, revisions, spectra, plots, classifications and HTML | Ignored |
| `runs/DATE/pyraf/` | IRAF working copies, products and logs | Ignored |
| `runs/development/` | Build/test staging and verification evidence | Ignored |
| `runs/publication/` | Temporary publishing clones | Ignored |
| `runs/archive/` | Retained cleanup evidence and deployment receipts | Ignored |

## Rules for new output

- Night-specific results go under the observing date, including delivery packages.
  Preserve revisions and the nightly report contract in the [epoch workflow](guides/epoch-workflow.md).
- Build deliverables go in `runs/development/build/`. CI test reports and metrics
  go in `runs/development/test-results/` and `runs/development/badge-data/`.
- Keep publication copies in `runs/publication/`; pushing code does not publish
  a local night. Published snapshots use `gh-pages`, as described in the
  [published index](../OUTPUTS_PIPELINE.md).
- Do not recreate top-level `outputs/`, `manuals_pessto/` or `wiserep_tns_upload/`.
  Their ignore rules remain as protection against accidental legacy writes.
- Software environments are not output: use the dedicated external EFOSpec
  environment or `.venv/` for development. Disposable tool caches and packaging
  intermediates can use their tool-standard ignored locations.

## Preserved dependencies and older records

`trunk` is an inherited folder name, not another Git branch or duplicate of the
active engine. CLI defaults, nightly setup, revision helpers and desktop
installation still use `trunk/src/ntt`. Keep this legacy baseline intact.

Unique development and deployment records are retained in
`runs/archive/repository-maintenance-20261127/`. The obsolete test environment,
rebuildable packages and two clean publication clones were removed. Both clone
heads matched their remote `gh-pages` branches; hosted reports are unchanged.

`runs/development/` and `runs/publication/` are temporary staging destinations,
not required local directories. They are absent after cleanup and may be
recreated by an explicit build, test or publishing job. Retain useful receipts
under `runs/archive/`, then remove disposable staging copies.

Archived records retain their original bytes and can mention old absolute
paths. The migration receipts provide source-to-destination maps. Use current
guides for commands; archived scripts and environments are not active tooling.

## Night folders and compatibility shortcuts

- `efospec/nightly/` contains processing revisions and `current.json`, which
  selects the revision used by the nightly log.
- `efospec/QC/` contains quality-control diagnostics and reviewed experiments.
  Revision-specific diagnostics can also live inside a nightly revision.
- `pyraf/` contains IRAF/PyRAF working copies and products. New `prepare_iraf.py`
  invocations use this name; the independent PESSTO checkout/environment and
  original product names are unchanged.
- October 28's formerly loose `QC/` and `nightly/` contents now live under
  `efospec/`. Its former `pessto/` directory is now `pyraf/`.
- November 10's older report bundle, assets and `nightly/` are retained under
  `efospec/archive/legacy-root/`. Its old pointer selects a different revision;
  it does not replace the current EFOSpec pointer.
- The 2024-11-14 and 2026-10-29 report/product trees now reside under `efospec/`.
  Their former paths remain compatibility shortcuts.
- November 26 already follows this layout. Its saved log attempt failed before
  reduction; that status and diagnostic evidence are retained.

Old `efosc`, root `QC`/`nightly`, and `pessto` entries are **compatibility
shortcuts**, not additional copies. Saved manifests, aperture databases and
reports still reference those paths. Keep these aliases until their consumers
have an explicit migration; new work must use the canonical directories.
File hashes and selected reports/pointers were preserved. The migration receipt
is `runs/archive/repository-maintenance-20261127/development-evidence/housekeeping/docs-layout-20261127/run-verification.json`.

Historical classifications under `data/` remain at their recorded paths. No
spectra were re-extracted during this cleanup. Per-night checksum receipts are
in `runs/archive/repository-maintenance-20261127/DATE/verification.json`.
