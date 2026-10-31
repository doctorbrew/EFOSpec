# EFOSpec — EFOSC2 spectroscopy with PypeIt

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

[Engine boundaries](docs/pipeline-stages.md) · [Extraction workbench](docs/gui.md)

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
  python -m efospec reduce-rapid ../pessto/2024-11-14 --output runs/my-night
```

- **One source:** add `--target SN2023xxj`.
- **New reduction:** choose a fresh output directory.
- **Review:** open **`runs/my-night/index.html`**.
- **Plots:** spectrum, 2D trace, and spatial profiles appear side by side.

- `products/`: legacy-named flux FITS and ASCII spectra.
- `native/`: PypeIt spec1d files and saved detector/sky/trace arrays.
- `style-preview/`: PDF/JPG diagnostics; `run.json` records source details.

Rebuild the page without repeating extraction:

```sh
python -m efospec report runs/my-night
# Use --existing-plots to rebuild HTML alone.
```

## Adjust an extraction

```sh
efospec gui runs/my-night
```

- Click trace anchors; adjust FWHM, aperture, and background bands.
- Extract one or two separated sources; inspect optimal and boxcar spectra.
- Save/reload recipes; originals stay unchanged in new revisions.
- [GUI and headless replay](docs/gui.md).

Check raw inputs for the future native path:

```sh
python -m efospec native-readiness ../pessto/2024-11-14 /path/to/raw-calibrations
```

- Missing/incompatible calibrations return a nonzero status; no archive fallback.
- Current night: raw standards present; raw arcs/biases/flats absent.
- Gr13 raw calibration candidates have now been retrieved separately; [locations and checks](docs/native-calibration.md#raw-gr13-inputs-now-retrieved).
- This checks inputs; it does not execute native reduction.

## Current limits

- Tested night: **13 science exposures**, Gr11/Gr13, Free filter, 2×2 binning.
- Calibration: archived IRAF arc IDs and sensitivity; no fresh masters.
- Not applied: bias, flat, dark, overscan, or telluric corrections.
- Target identity: nominal-position choices remain flagged until verified.
- Products: experimental; no ESO Phase 3 certification.
- GUI: saved detector window; separated traces only, without SN/host deblending.

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
