# ePESSTO+ — EFOSC2 spectroscopy with PypeIt

An experimental migration of the PESSTO optical spectroscopy pipeline. PypeIt
handles source tracing, sky modelling, and optimal/boxcar extraction; our Python
code applies archived wavelength and flux calibrations and preserves legacy
FITS/ASCII filenames. IRAF/PyRAF is not executed. SOFI is a later phase.

## Install

Keep the source checkout: plotting and archived calibration references live here.
Use a separate environment with the tested PypeIt 1.14.0 engine:

```sh
git clone https://github.com/sPaMFouR/epessto-plus.git
cd epessto-plus
conda create -n epessto-plus python=3.11 pip
conda activate epessto-plus
python -m pip install 'numpy==1.26.4' 'astropy==6.1.1' 'scipy==1.14.0' -e '.[rapid,plots]'
```

Plots also require LaTeX: `latex`, `dvipng`, and `type1cm`/`cm-super` (TeX Live
or MacTeX). Existing PypeIt environments can be used instead. If plotting uses
another environment, set `EPESSTO_PLOT_PYTHON` to that Python executable.
The current checks use existing environments; the fresh-install recipe above
has not yet been validated in a clean environment.

## Reduce a night

From the repository root, put the raw EFOSC2 FITS files in a night directory
outside this checkout. Example for the demonstrated night (data are not bundled):

```sh
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m epessto_plus reduce-rapid ../2024-11-14 --output runs/my-night
```

Add `--target SN2023xxj` to select one source. Choose a fresh output directory
for each reduction. Open **`runs/my-night/index.html`** for the Fieldnotes table
and side-by-side spectrum, 2D trace, and spatial-profile plots.

- `products/`: legacy-named flux FITS and ASCII spectra.
- `native/`: PypeIt spec1d files and saved detector/sky/trace arrays.
- `style-preview/`: PDF/JPG diagnostics; `run.json` records source details.

Rebuild the page without repeating extraction:

```sh
python -m epessto_plus report runs/my-night
# Use --existing-plots to rebuild HTML alone.
python -m unittest discover -s tests -v
```

## Current limits

Demonstrated on 13 science exposures from 2024-11-14: EFOSC2 Gr11/Gr13, Free
filter, 2×2 binning. This rapid mode uses archived IRAF arc IDs and sensitivity;
it does not build fresh calibration masters or apply bias, flat, dark, overscan,
or telluric corrections. Nominal-position target choices remain flagged until
verified. Products are experimental, not ESO Phase 3 certified.

[Commands and details](EPESSTO_PLUS.md) · [Pipeline stages](docs/pipeline-stages.md) ·
[Migration plan](docs/roadmap/pypeit-migration/README.md) ·
[Legacy PyRAF installation](docs/legacy-installation.md)

The preserved upstream pipeline and calibration library are under `trunk/`;
new code is under `src/epessto_plus/`, with scripts in `scripts/` and tests in
`tests/`. Raw data, local runs, and generated outputs are excluded from Git.
