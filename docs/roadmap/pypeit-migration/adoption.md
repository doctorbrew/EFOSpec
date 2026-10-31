# EFOSpec and observer migration

## Scope and name

- EFOSC2 optical spectroscopy only.
- **EFOSpec:** EFOSC2 spectroscopy with PypeIt.
- Distribution, Python module, command, and Conda environment: `efospec`.
- Repository: [sPaMFouR/EFOSpec](https://github.com/sPaMFouR/EFOSpec).
- EFOSpec is the software name; ePESSTO remains the collaboration name.
- The planned GUI shares the EFOSpec name.

## Dedicated runtime

```sh
# From the repository root:
conda env create -f environment.yml
conda activate efospec
python -m efospec --help
```

- Python 3.11; dependencies come from `pyproject.toml` with the `rapid,plots` extras.
- `constraints.txt` pins the tested numeric stack and PypeIt 1.14.0.
- `constraints-ci.txt` includes the same pins for existing CI commands.
- Conda uses conda-forge; the old AstroConda channel is not inherited.
- This is a fresh install, not a clone of `pessto` or `pypeit`.
- No IRAF/PyRAF, STScI bundle, SWarp, SExtractor, PyNOT, or unrelated science packages are requested.
- PypeIt's mandatory dependencies include Qt/Ginga/IPython; keep them for a supported installation.
- PypeIt 1.14 also needs `pkg_resources`; we pin Setuptools 80.9.0 ([removal in 82](https://setuptools.pypa.io/en/stable/deprecated/pkg_resources.html)).
- Runtime excludes our `test` extra; tests and build tools belong in a separate development environment.
- System requirements: `gzip` for ESO downloads; LaTeX, `dvipng`, and required fonts for plots.
- Numeric pins are shared across platforms; this is not a complete transitive dependency lock.
- To choose another environment name: `conda env create -n YOUR_NAME -f environment.yml`.

## Earlier runtime verification — 2026-10-31

- Fresh macOS ARM64 runtime: Python 3.11.18, PypeIt 1.14.0, shared pinned dependencies.
- Dependency checks and wheel build passed; **92 tests passed** in a separate development overlay.
- Runtime has no installed IRAF/PyRAF, `ntt`, PyNOT, pytest, coverage plugin, or `build` distribution.
- SN2023xxj: one successful extraction, complete HTML report, four PDF/JPG diagnostic pairs.
- Local report: `runs/slitcraft-runtime-SN2023xxj-verified/index.html` (ignored by Git).
- Legacy filename, wavelength grid, units, and validity masks match the earlier PypeIt run.
- Optimal flux differs by 0.019% in relative L2 norm; recorded aperture edges differ by 0.004 pixel.
- The earlier run used NumPy 2.1.3; this runtime pins 1.26.4. Bitwise reproducibility is not established.
- Evidence: `runs/slitcraft-runtime-evidence.json`; this remains an archive-calibration demonstration.

## EFOSpec rename verification

- **97 tests passed:** includes old/new commands, module aliases, saved instrument identity, and plotting-variable precedence.
- New SN2023xxj reduction: all four spectral arrays, masks, and scientific headers match the pre-rename runtime exactly.
- Report: `runs/efospec-rename-SN2023xxj/index.html`; four PDF/JPG diagnostic pairs.
- Existing Fieldnotes pages use EFOSpec branding; their science products remain unchanged.
- Evidence: `runs/efospec-rename-verification.json` (local, ignored by Git).

## Migration for existing PESSTO users

1. Keep the working `pessto` environment for reproducing legacy results.
2. Create the new environment from `environment.yml`; do not upgrade the old environment in place.
3. Use the same raw-night directory, ESO credentials, and target names.
4. Write new reductions into a fresh run directory; inspect its Fieldnotes report.
5. Compare target identity, wavelength/flux calibration, aperture/background, and uncertainty.
6. Switch routine observing only after the native calibration and delivery checks pass.

| Existing habit | New workflow available now |
| --- | --- |
| Activate the legacy `pessto` environment | `conda activate efospec` |
| Retrieve a raw night manually | `python -m efospec download YYYY-MM-DD` |
| Run the rapid legacy command | `python -m efospec reduce-rapid NIGHT --output runs/RUN` |
| Inspect plots separately | Open `runs/RUN/index.html` |
| Check calibration availability | `python -m efospec native-readiness NIGHT CALIBRATIONS` |

- `reduce-rapid` remains the explicit archive-calibration experiment.
- The clean environment needs no IRAF runtime, but the current reducer still reads IRAF-derived calibration references.
- Native raw-arc wavelength fitting and observed-standard sensitivity generation remain required before production migration.
- Old `PESSTOFASTSPEC` commands are not silently redirected: their arguments and scientific behaviour differ.
- Preserve legacy FITS/ASCII names, units, and wavelength conventions when adopting a new brand.

## Upgrade an existing installation

```sh
# In your existing checkout:
git remote set-url origin https://github.com/sPaMFouR/EFOSpec.git
git pull --ff-only
conda env create -f environment.yml
conda activate efospec
efospec --help
```

- Existing installations should use the new environment; leave the legacy `pessto` environment intact.
- If reusing the provisional environment, deactivate it, then run `conda rename -n slitcraft efospec`.
- After renaming it, activate `efospec` and run `python -m pip uninstall epessto-plus`.
- Remove stale generated metadata with `rm -rf src/epessto_plus.egg-info` from the repository root.
- Install with `python -m pip install -c constraints.txt -e '.[rapid,plots]'`.
- `epessto-plus` and `python -m epessto_plus` remain compatibility entry points.
- Old `epessto_plus` imports forward to the same `efospec` modules; reduction logic is not duplicated.
- Prefer `EFOSPEC_PLOT_PYTHON`; the old `EPESSTO_PLOT_PYTHON` variable remains a fallback.
- Selection order: `--plot-python`, new variable, old variable, current interpreter.
- Product names, calibration paths, and the saved `PYP_SPEC` identifier remain stable.
- Local checkouts are siblings: `/Users/avinash/Work/Reduction/EFOSpec` and `/Users/avinash/Work/Reduction/pessto`.
- The former nested checkout and `epessto+` symlink have been removed.
- Existing raw data stay in `../pessto/2024-11-14`; new downloads use EFOSpec's `data/` folder.
- Moved runs resolve their own product/native files; missing local files are reported instead of using another copy.
- Historical manifests and source snapshots retain their original names and hashes.
- After moving a checkout, reinstall with the pinned editable-install command above; recreate development virtual environments.
- Relocation verified: **100 tests passed**, SN2023xxj plots regenerated, and hashes unchanged for 258 saved run files and 15 raw inputs.
- Local relocation evidence: `runs/relocation-verification.json`.
