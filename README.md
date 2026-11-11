# EFOSpec — EFOSC2 spectroscopy with PypeIt

<img src="docs/brand/efospec-logo.png" alt="EFOSpec: slit and spectral-wave emblem" width="580">

[![python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](pyproject.toml)
[![build](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml)
[![tests](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FsPaMFouR%2FEFOSpec%2Fbadges%2Ftests.json)](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml)
[![coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FsPaMFouR%2FEFOSpec%2Fbadges%2Fcoverage.json)](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml)

EFOSC2 optical spectroscopy with a PySide6 desktop editor and a read-only nightly log.

- **Runtime:** Python 3.11, PypeIt 3.0.0; no IRAF/PyRAF process required.
- **Scientific status:** experimental. New nightly revisions use raw bias/flat/arc calibrations and same-night standard responses.
- **Desktop:** spectra and failed-exposure review in one application; recipes save new revisions.

## Install

```sh
git clone https://github.com/sPaMFouR/EFOSpec.git
cd EFOSpec
conda env create -f environment.yml
conda activate efospec
```

- Keep the checkout and environment: plotting code and calibration references live there.
- Install LaTeX, `dvipng`, and `type1cm`/`cm-super` for scientific figures.
- Keep the original `pessto/` checkout beside `EFOSpec/`.
- [Existing-user migration](docs/roadmap/pypeit-migration/adoption.md) · [Installation details](EFOSPEC.md).

## Download and reduce one night

```sh
efospec download 2026-10-28 --with-calibrations
efospec night 2026-10-28
```

- Run from the checkout; downloads go to `data/2026-10-28/`.
- Archive access uses `ESO_USERNAME` / `ESO_PASSWORD`, or `ESO_TOKEN`.
- Open **`runs/2026-10-28/index.html`** for the observing table, spectra and diagnostics.
- The self-contained page includes observations, spectra, issues, source/background QC, calibrations and archive summaries.
- Partial reductions retain failed/unsupported exposures in the report.
- Each invocation names one observing date; previous processing revisions remain intact.
- **Calibration mode:** new `night` revisions default to `--flux-calibration same-night`. Use `--flux-calibration archive` explicitly for the legacy calibration bridge; existing revisions retain their recorded policy. Missing or failed same-night standards do not trigger an archive fallback.
- [Dated workflow and separate stages](docs/epoch-workflow.md) · [Raw calibration commands and limits](docs/native-raw-run.md).

### Compare existing IRAF reductions

Keep the historical IRAF FITS products beside the raw files in `data/DATE/`
(subfolders are searched), then add the optional flag:

```sh
efospec night 2024-11-14 --iraf-comparison
# Add comparisons to an existing selected reduction without re-extracting:
efospec night 2024-11-14 --stage report --iraf-comparison
```

The nightly **IRAF comparison** link opens `runs/DATE/iraf-comparison.html`,
which shows matched flux spectra and unmatched or
unsupported products. Matching uses FITS provenance and exposure metadata, not
object names alone. No flux rescaling or wavelength alignment is applied, and
neither the reduction engine nor the historical files are changed. The main
nightly spectrum panels remain PypeIt-only.

## Inspect and extract

```sh
efospec gui runs/2026-10-28
# Optional desktop icon, using this same environment:
efospec install-desktop
```

1. **Spectra:** inspect a completed spectrum, trace and spatial profiles.
2. Edit the source, aperture and background; save a recipe and extract a new revision.
3. **Source review:** open a failed exposure's QC packet and choose the trace explicitly.
4. Review the new products; saving or extracting in the GUI does **not** select that revision for the nightly webpage.
5. Follow [publishing reviewed geometry](docs/epoch-workflow.md#gui-revisions-and-nightly-publication) to run a new dated reduction with an explicit reviewed-source record. Rebuilding HTML alone does not promote a GUI extraction.

- Opens dated folders, individual reductions, or `review.json` packets.
- macOS `.app` / Linux launcher use the dedicated environment; no separate runtime is bundled.
- Failed-exposure polynomial extraction currently produces count-level boxcar spectra.
- [Desktop guide](docs/desktop.md) · [Launcher installation](docs/desktop-installation.md) · [Validation results](docs/validation-desktop-2026-11.md).

## Scientific boundaries

| Component | Responsibility |
| --- | --- |
| PypeIt | Tracing, sky fitting, optimal/boxcar extraction; raw master construction in native mode |
| EFOSpec | Input checks, calibration association, product naming, recipes, GUI and nightly reports |
| Experimental joint solver | Fixed spatial profiles, polynomial background and conditional source covariance |

- Original product names, calibration associations and wavelength conventions are preserved.
- Raw-only calibration is a separate validation effort; recent-night reductions remain partial.
- Joint SN/companion recovery passes matched-profile tests; real host separation is **not validated**.
- No telluric/slit-loss correction or ESO Phase 3 certification.
- [Pipeline machinery, including IRAF](docs/figures/reduction-machinery.svg) · [Engine boundaries](docs/pipeline-stages.md) · [Roadmap](docs/roadmap/pypeit-migration/gui.md).

## Repository guide

Start with [the project index](docs/PROJECT_INDEX.md) for a route through the
code and documentation. Use [the contributor guide](docs/contributing.md) for
setup, checks and the boundary between display changes and scientific changes.

| Location | Purpose |
| --- | --- |
| `src/efospec/` | Active Python pipeline, desktop GUI and report generators |
| `scripts/` | Dated workflow entry points and explicit diagnostic tools |
| `tests/` | Automated regression checks |
| `docs/` | Workflow, calibration, GUI and validation documentation |
| `trunk/` | Preserved legacy engine and bundled calibration references |
| `trunk/legacy-tools/` | Historical IRAF/PyRAF installation helpers and notes |
| `data/DATE/` | Local raw inputs and historical comparison products; ignored by Git |
| `runs/DATE/` | Local nightly reports, revisioned reductions and QC; ignored by Git |
| `outputs/` | Local development experiments and archived housekeeping evidence; ignored by Git |

The last three directories are local working data, not package source. Historical
paths under `runs/` can remain dependencies of saved recipes; use each dated
`index.html` as the entry point rather than choosing folders by modification time.

## Development

- `src/efospec/`: active pipeline; `trunk/`: preserved original code and references.
- `tests/`: automated checks; [test environment and CI](docs/ci.md).
- `data/`, `runs/`, and `outputs/`: local, gitignored observing data and results.
- Default-branch CI publishes the test/coverage badges; PR runs do not replace them.
- [Commands](EFOSPEC.md) · [Legacy installation](docs/legacy-installation.md).
