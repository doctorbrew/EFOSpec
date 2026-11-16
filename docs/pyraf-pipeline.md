# Native Python PyRAF pipeline

Development branch: `pyraf-pipeline`, in the original `pessto` checkout.
The EFOSpec/PypeIt checkout and its environment are separate.
New IRAF attempts are stored in `../EFOSpec/runs/DATE/pessto/iraf-full-NN/`;
EFOSpec outputs are in `../EFOSpec/runs/DATE/efosc/`. Use the manual
`prepare_iraf.py` helper to copy raw inputs into a new IRAF attempt. Historical
`runs/pyraf-debug/` paths below are retained validation evidence, not the new
nightly output destination.

## Start the installed environment

```sh
cd /Users/avinash/Work/Reduction/pessto
source .venv-pyraf/bin/activate
export iraf=/usr/local/lib/iraf/
PESSTOFASTSPEC --version
PESSTOFASTSPEC -h
PESSTOEFOSC2dSPEC -h
PESSTOEFOSC1dSPEC -h
```

The new environment uses native ARM CPython 3.11, PyRAF 2.2.4, NumPy
1.26.4, Astropy 6.1.7, SciPy 1.14.1 and matplotlib 3.9.4, with the installed
ARM IRAF executables. It does not use the broken Intel Python 3.7 `pessto`
conda environment. NumPy 2 and newer Python versions are not yet validated.

To reproduce the environment with a native Python 3.11 interpreter:

```sh
python3.11 -m venv .venv-pyraf
.venv-pyraf/bin/python -m pip install -c constraints-pyraf.txt -e ./trunk pytest
```

IRAF is an external prerequisite, not a pip dependency. Set `iraf` to its
actual installation root. macOS PyRAF also installs its PyObjC dependencies.
The runtime snapshot is retained under `runs/pyraf-debug/environment-freeze.txt`.
Official installation references: [PyRAF](https://pyraf.readthedocs.io/en/latest/pyraf_tutorial.html#installation)
and [IRAF](https://iraf-community.github.io/install.html).

## Repeatable reduction debugging

The runner copies inputs into a new directory, isolates the PyRAF code cache,
disables display for the subprocess, captures logs, imposes a timeout, and
checks original input hashes. It refuses an existing output directory.
No raw file or accepted reduction is replaced. Run from the repository root:

```sh
.venv-pyraf/bin/python scripts/debug_reduction.py fast \
  --input pessto_test/EFOSC.2012-04-12T00:21:13.429.fits \
  --output ../EFOSpec/runs/2012-04-11/pessto/NEW-fast-trial
```

For a full reduction, repeat `--input` for the science, standard, bias,
matching flat and arc frames. Use `full2d`, then `full1d` with the calibrated
2D science/standard outputs. These stages are deliberately separate: inspect
2D calibration before extraction. The runner is a debugging tool, not a
reviewed batch-release workflow. Missing-calibration prompts fail on EOF
rather than receiving automatic scientific choices.

For interactive operation, use fresh working copies with the installed
commands and `-i`. Do not set `PYRAF_NO_DISPLAY` in the interactive shell.
Use the existing reduction manual for aperture and calibration review.

## Fixes established by reproductions

- Modern isolated pip builds previously failed because setup.py required
  runtime NumPy in the build environment. Added PEP 517 packaging and real
  runtime dependency metadata; removed obsolete `imp`/distutils setup hooks.
- Fixed the relative version import (`unknown` became `3.0.1`).
- Importing `ntt` previously forced TkAgg over an explicitly selected Agg
  backend. Preserve the caller's backend; regression observed failing then passing.
- Batch fast/standard wavelength checks now respect their interactive flag.
- Full reduction failed when resolution and atmospheric cursor scripts opened
  an interactive graphics device. Save their IRAF GKI streams through
  `StdoutG`; the measurement/extraction tasks still run. GKI files are diagnostic
  task records, not house-styled publication plots.
- A synthetic physical-unit regression demonstrated that the 2D product's
  old `10^20` BUNIT implied a factor of 10^40 error when interpreting its
  scaled array. Corrected the label to `1e-20 erg / (s cm2 Angstrom)` without
  changing array values or the calibration algorithm.
- Full 1D reduction's IRAF header-delete call prompted for a value and wrote
  `PRODCATG=1`. Explicit Astropy removal preserves the original intended
  deletion and avoids the query.

## Checks completed on 14 November 2026

- Editable installation and all three spectroscopy CLI help commands work.
- `pip check` passes; focused regression tests pass.
- Fast test: LSQ12btn, exposure `EFOSC.2012-04-12T00:21:13.429.fits`.
  Four expected outputs produced. All four FITS bands finite; ASCII and FITS
  primary spectrum agree within text precision. 1D arrays are identical
  before/after the compatibility fixes. Evidence: `runs/pyraf-debug/attempt-02/`.
- Full test: observing night 2026-10-28, Gr13/Free/slit1.0, AT2024afzf
  (`EFOSC.2026-10-29T07:12:15.228.fits`) and vma2
  (`EFOSC.2026-10-29T02:31:38.734.fits`), with 21 selected raw inputs total.
  Full 2D completes in `runs/pyraf-debug/full2d-03/`; full 1D completes in
  `runs/pyraf-debug/full1d-03/`. Exact source inventories, hashes, return codes
  and output inventories are in each `verification.json`.
- Real Tk cursor events now exercise aperture limits, background windows, trace
  refitting and extraction from the saved database. See [validation evidence](pyraf-validation.md).

## Interactive and scientific validation

The follow-up used 52 raw frames across Gr11/Free, Gr13/Free, Gr13/GG495 and
Gr16/OG530, all with slit1.0. It found and fixed multi-standard prompting,
incorrect atmospheric-standard association, cached IRAF wavelength headers,
and missing telluric propagation of extraction uncertainty. The real IRAF
regressions include the `BANDID4=sigma` convention, not just unlabeled arrays.

The diagnostic reductions are **not scientifically approved**. Automated
aperture selection and the Gr11 wavelength solution need review; extraction
uncertainties also contain invalid values in the Gr11 trial. Physical mouse
operation, DS9 display, independent arc validation, absolute flux/slit losses,
other slits, SOFI and imaging remain unverified. Fractional wavelength shifts
still use the legacy integer-Angstrom application.

See [the validation report and repeat commands](pyraf-validation.md) for the
measured results, saved editor evidence and house-styled PDF/JPG diagnostics.

No commit or push was made. Existing unrelated working-tree changes were retained.
