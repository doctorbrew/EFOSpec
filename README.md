# EFOSpec — EFOSC2 spectroscopy with PypeIt

<img src="docs/brand/efospec-logo.png" alt="EFOSpec: slit and spectral-wave emblem" width="580">

[![python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](pyproject.toml)
[![build](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml)
[![tests](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FsPaMFouR%2FEFOSpec%2Fbadges%2Ftests.json)](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml)
[![coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FsPaMFouR%2FEFOSpec%2Fbadges%2Fcoverage.json)](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml)

- **Scope:** EFOSC2 optical spectroscopy only.
- **PypeIt:** tracing, sky modelling, optimal and boxcar extraction.
- **Our code:** archived calibration, legacy filenames, diagnostics, and reports.
- **Status:** experimental; no IRAF/PyRAF execution, but archived IRAF calibrations remain.
- **Native calibration:** required next; [inputs and remaining work](docs/native-calibration.md).

![Legacy IRAF and current PypeIt reduction paths](docs/figures/reduction-machinery.svg)

[Engine boundaries](docs/pipeline-stages.md) · [Desktop GUI roadmap](docs/roadmap/pypeit-migration/gui.md)

## Install

- Keep the checkout: it contains plotting code and archived references.
- Use the dedicated Python 3.11 environment and **PypeIt 1.14.0** engine.

```sh
git clone https://github.com/sPaMFouR/EFOSpec.git
cd EFOSpec
conda env create -f environment.yml
conda activate efospec
```

- **Plot dependencies:** LaTeX, `dvipng`, and `type1cm`/`cm-super`.
- **Package, command, and environment:** `efospec`.
- **Migration:** [environment, naming, and observer transition](docs/roadmap/pypeit-migration/adoption.md).
- **Dependencies:** project extras plus shared scientific pins in `constraints.txt`.
- **Separate plotting Python:** set `EFOSPEC_PLOT_PYTHON` to its executable.
- **Existing scripts:** old commands and imports remain compatibility aliases; see the migration guide.
- **CI:** Python 3.11 build, tests, and plot rendering; [details](docs/ci.md).

Keep the two checkouts beside each other:

```text
Reduction/
├── pessto/   # original pipeline and existing raw data
└── EFOSpec/  # independent repository, downloads, and new reductions
```

## Download a night

```sh
python -m efospec download 2026-10-29
```

- Saves raw EFOSC2 exposures in **`data/2026-10-29/`**.
- Uses exported `ESO_USERNAME` / `ESO_PASSWORD`, or `ESO_TOKEN`.
- Observing night: noon UTC on the given date to noon the following day.
- Optional: `--programme 117.29T8.002`, `--spectra-only`, `--dry-run`.
- `--with-calibrations`: adds associated raw inputs under `calibrations/`, including other dates.
- Repeating the command verifies and reuses completed FITS; failures return nonzero.
- [Authentication and download details](EFOSPEC.md#download-raw-data).

## Run the archive-based demonstration

- Run from the repository root.
- Keep raw FITS in a separate night directory; data are not bundled.
- Example: the demonstrated 2024-11-14 night.

```sh
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m efospec reduce-rapid ../pessto/2024-11-14 --output runs/2024-11-14
```

- **One source:** add `--target SN2023xxj`.
- **New reduction:** choose a fresh output directory.
- **Review:** open **`runs/2024-11-14/index.html`**.
- **Plots:** spectrum, 2D trace, and spatial profiles appear side by side.

- `products/`: legacy-named flux FITS and ASCII spectra.
- `native/`: PypeIt spec1d files and saved detector/sky/trace arrays.
- `style-preview/`: PDF/JPG diagnostics; `run.json` records source details.

Rebuild the page without repeating extraction:

```sh
python -m efospec report runs/2024-11-14
# Use --existing-plots to rebuild HTML alone.
```

## Desktop extraction and nightly reports

- **Desktop GUI — planned:** trace, aperture, background, and extraction controls in a desktop application.
- **Toolkit — open:** Swift/SwiftUI for macOS or a suitable desktop toolkit for macOS/Linux.
- **Fieldnotes webpage — available:** read-only nightly log, opening table, per-source plots, and downloads.
- **Browser editor — prototype:** `efospec gui` currently opens a browser; it does not deliver the requested desktop app.
- [Desktop roadmap](docs/roadmap/pypeit-migration/gui.md) · [Prototype instructions](docs/gui.md) · [Project rules](AGENTS.md).

## Native calibration readiness

Check raw inputs for the future native path:

```sh
python -m efospec native-readiness ../pessto/2024-11-14 /path/to/raw-calibrations
```

- Missing/incompatible calibrations return a nonzero status; no archive fallback.
- Original 2024-11-14 directory: raw standards present; raw arcs/biases/flats absent.
- Gr13 raw calibration candidates have now been retrieved separately; [locations and checks](docs/native-calibration.md#raw-gr13-inputs-now-retrieved).
- October 2026 nights: raw candidates available; [download and reduction checks](docs/validation-2026-10.md).
- This checks inputs; it does not execute native reduction.

## Current limits

- Initial demonstration: **13 science exposures**, Gr11/Gr13, Free filter, 2×2 binning.
- Recent nights: partial reductions; weak sky lines, unsupported setups, and source selection still stop exposures.
- Calibration: archived IRAF arc IDs and sensitivity; no fresh masters.
- Not applied: bias, flat, dark, overscan, or telluric corrections.
- Target identity: nominal-position choices remain flagged until verified.
- Products: experimental; no ESO Phase 3 certification.
- Desktop GUI: not implemented; the browser prototype is retained for backend development.
- Manual backend: saved detector window and separated sources; no SN/host deblending.

[Commands and details](EFOSPEC.md) · [Pipeline stages](docs/pipeline-stages.md) ·
[Migration plan](docs/roadmap/pypeit-migration/README.md) ·
[Tests and CI](docs/ci.md) ·
[Legacy PyRAF installation](docs/legacy-installation.md)

| Location | Contents |
| --- | --- |
| `trunk/` | Preserved legacy pipeline and calibration library |
| `src/efospec/` | New reduction and reporting code |
| `scripts/` | Plotting and diagram generators |
| `tests/` | Automated checks |

Raw data, local runs, and generated outputs stay outside Git.
