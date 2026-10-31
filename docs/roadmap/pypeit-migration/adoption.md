# Package identity and observer migration

## Scope and name

- EFOSC2 optical spectroscopy only.
- **Slitcraft:** recommended working name; slit spectroscopy, trace selection, and extraction.
- **EFOSpec:** alternative; clear instrument focus, less distinctive.
- Use “EFOSC2 reduction for ePESSTO” as the subtitle, not the package name.
- `slitcraft` is the provisional environment name; the package is still `epessto-plus`.
- The checkout remains `epessto+`; the public repository has not been renamed.
- Current commands and imports remain compatible while the final name is chosen.
- Initial name checks: neither candidate had an exact PyPI package or GitHub repository-name search result.
- These checks describe the current registries, not a reservation or ownership claim.

## Dedicated runtime

```sh
# From the repository root:
conda env create -f environment.yml
conda activate slitcraft
python -m epessto_plus --help
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

## Local verification — 2026-10-31

- Fresh macOS ARM64 runtime: Python 3.11.18, PypeIt 1.14.0, shared pinned dependencies.
- Dependency checks and wheel build passed; **92 tests passed** in a separate development overlay.
- Runtime has no installed IRAF/PyRAF, `ntt`, PyNOT, pytest, coverage plugin, or `build` distribution.
- SN2023xxj: one successful extraction, complete HTML report, four PDF/JPG diagnostic pairs.
- Local report: `runs/slitcraft-runtime-SN2023xxj-verified/index.html` (ignored by Git).
- Legacy filename, wavelength grid, units, and validity masks match the earlier PypeIt run.
- Optimal flux differs by 0.019% in relative L2 norm; recorded aperture edges differ by 0.004 pixel.
- The earlier run used NumPy 2.1.3; this runtime pins 1.26.4. Bitwise reproducibility is not established.
- Evidence: `runs/slitcraft-runtime-evidence.json`; this remains an archive-calibration demonstration.

## Migration for existing PESSTO users

1. Keep the working `pessto` environment for reproducing legacy results.
2. Create the new environment from `environment.yml`; do not upgrade the old environment in place.
3. Use the same raw-night directory, ESO credentials, and target names.
4. Write new reductions into a fresh run directory; inspect its Fieldnotes report.
5. Compare target identity, wavelength/flux calibration, aperture/background, and uncertainty.
6. Switch routine observing only after the native calibration and delivery checks pass.

| Existing habit | New workflow available now |
| --- | --- |
| Activate the legacy `pessto` environment | `conda activate slitcraft` |
| Retrieve a raw night manually | `python -m epessto_plus download YYYY-MM-DD` |
| Run the rapid legacy command | `python -m epessto_plus reduce-rapid NIGHT --output runs/RUN` |
| Inspect plots separately | Open `runs/RUN/index.html` |
| Check calibration availability | `python -m epessto_plus native-readiness NIGHT CALIBRATIONS` |

- `reduce-rapid` remains the explicit archive-calibration experiment.
- The clean environment needs no IRAF runtime, but the current reducer still reads IRAF-derived calibration references.
- Native raw-arc wavelength fitting and observed-standard sensitivity generation remain required before production migration.
- Old `PESSTOFASTSPEC` commands are not silently redirected: their arguments and scientific behaviour differ.
- Preserve legacy FITS/ASCII names, units, and wavelength conventions when adopting a new brand.

## Rename rollout after name selection

- Add the chosen console command; retain `epessto-plus` as a compatibility alias.
- Offer the new Python module while preserving existing `epessto_plus` imports initially.
- Update package metadata, report branding, installer examples, and environment name together.
- Rename the public repository only as an explicit final step; update badge and documentation URLs.
- Test both command names against identical inputs and unchanged output naming.
- Keep GUI work on the [existing extraction roadmap](gui.md); do not bundle a speculative GUI stack into the runtime.
