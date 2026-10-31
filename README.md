# ePESSTO+ — EFOSC2 spectroscopy with PypeIt

[![python](https://img.shields.io/badge/python-%3E%3D3.9-blue)](pyproject.toml)
[![build](https://github.com/sPaMFouR/epessto-plus/actions/workflows/build.yml/badge.svg?branch=master)](https://github.com/sPaMFouR/epessto-plus/actions/workflows/build.yml)

- **Scope:** EFOSC2 optical spectroscopy; SOFI later.
- **PypeIt:** tracing, sky modelling, optimal and boxcar extraction.
- **Our code:** archived calibration, legacy filenames, diagnostics, and reports.
- **Status:** experimental; no IRAF/PyRAF execution, but archived IRAF calibrations remain.
- **Native calibration:** required next; [inputs and remaining work](docs/native-calibration.md).

![Legacy IRAF and current PypeIt reduction paths](docs/figures/reduction-machinery.svg)

[Engine boundaries](docs/pipeline-stages.md) · [GUI roadmap](docs/roadmap/pypeit-migration/gui.md)

## Install

- Keep the checkout: it contains plotting code and archived references.
- Use Python 3.11 and the tested **PypeIt 1.14.0** engine.

```sh
git clone https://github.com/sPaMFouR/epessto-plus.git
cd epessto-plus
conda create -n epessto-plus python=3.11 pip
conda activate epessto-plus
python -m pip install 'numpy==1.26.4' 'astropy==6.1.1' 'scipy==1.14.0' -e '.[rapid,plots]'
```

- **Plot dependencies:** LaTeX, `dvipng`, and `type1cm`/`cm-super`.
- **Existing environment:** the current `pypeit` Conda environment also works.
- **Separate plotting Python:** set `EPESSTO_PLOT_PYTHON` to its executable.
- **CI:** Python 3.11 build, tests, and plot rendering; [details](docs/ci.md).

## Run the archive-based demonstration

- Run from the repository root.
- Keep raw FITS in a separate night directory; data are not bundled.
- Example: the demonstrated 2024-11-14 night.

```sh
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m epessto_plus reduce-rapid ../2024-11-14 --output runs/my-night
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
python -m epessto_plus report runs/my-night
# Use --existing-plots to rebuild HTML alone.
```

Check raw inputs for the future native path:

```sh
python -m epessto_plus native-readiness ../2024-11-14 /path/to/raw-calibrations
```

- Missing/incompatible calibrations return a nonzero status; no archive fallback.
- Current night: raw standards present; raw arcs/biases/flats absent.
- This checks inputs; it does not execute native reduction.

## Current limits

- Tested night: **13 science exposures**, Gr11/Gr13, Free filter, 2×2 binning.
- Calibration: archived IRAF arc IDs and sensitivity; no fresh masters.
- Not applied: bias, flat, dark, overscan, or telluric corrections.
- Target identity: nominal-position choices remain flagged until verified.
- Products: experimental; no ESO Phase 3 certification.
- GUI: planned; manual editing and two-source export are not implemented yet.

[Commands and details](EPESSTO_PLUS.md) · [Pipeline stages](docs/pipeline-stages.md) ·
[Migration plan](docs/roadmap/pypeit-migration/README.md) ·
[Tests and CI](docs/ci.md) ·
[Legacy PyRAF installation](docs/legacy-installation.md)

| Location | Contents |
| --- | --- |
| `trunk/` | Preserved legacy pipeline and calibration library |
| `src/epessto_plus/` | New reduction and reporting code |
| `scripts/` | Plotting and diagram generators |
| `tests/` | Automated checks |

Raw data, local runs, and generated outputs stay outside Git.
