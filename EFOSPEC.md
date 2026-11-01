# EFOSpec operating notes

- **Install:** [compact README](README.md).
- **Science:** [engine boundaries](docs/pipeline-stages.md).
- **Design:** [migration plan](docs/roadmap/pypeit-migration/README.md).
- **Desktop GUI:** [PySide6 controls and usage](docs/desktop.md).
- **Browser editor:** [experimental prototype and recipe replay](docs/gui.md); not the desktop app.
- **Webpage:** read-only nightly log, separate from extraction controls.
- **Scope:** experimental EFOSC2 archive/raw-only reduction; PypeIt 1.14.0.
- **Native calibration:** [raw inputs and remaining work](docs/native-calibration.md).

## Download raw data

```sh
# Export these locally in your shell or ~/.zshrc; use your actual values there.
export ESO_USERNAME='your-eso-username'
export ESO_PASSWORD='your-eso-password'

python -m efospec download 2026-10-29
# Preview a programme-specific selection, including its raw calibration associations:
python -m efospec download 2026-10-29 --programme 117.29T8.002 --with-calibrations --dry-run
# Run the same command without --dry-run to download it.
```

- Open a new terminal after changing `.zshrc`; the downloader reads exported variables only.
- `.zshrc` stores literal passwords as plain text; Keychain can supply `ESO_PASSWORD` for persistent use.
- Optional `ESO_TOKEN` takes precedence; it also enables searches for protected metadata.
- Username/password authentication applies to file downloads; metadata queries remain anonymous.
- Proprietary files require **Data Access** rights for their programme.
- Default selection: all raw EFOSC2 exposures from noon UTC to the following noon.
- `--programme ID`: restrict the night query; no programme is hard-coded.
- `--spectra-only`: omit imaging/acquisition frames from that query.
- `--with-calibrations`: add associated raw exposures, possibly from other dates/programmes.
- Night frames: `data/YYYY-MM-DD/*.fits`; additional associations: `calibrations/*.fits`.
- Custom destination: `--output-root /path/to/data`; the date folder is added automatically.
- `--public-only`: ignore credentials; inaccessible files remain recorded as failed.
- ESO `.fits.Z` downloads require system `gzip`; `.fits.gz` and plain FITS also work.
- Downloads verify raw FITS identity, dates, completeness, available checksums, and SHA-256.
- `download-manifest.json` records each result; `--dry-run` writes `download-plan.json`.
- Resume by repeating the command; interrupted files restart, completed files are reused.
- Changed existing files are preserved and reported; they are never overwritten.
- One writer per date folder. After a killed process, remove `.download.lock` only once that writer has stopped.
- Exit codes: **0** complete/planned; **1** empty/incomplete; **2** invalid inputs or query/local failures.
- Credentials never enter URLs, manifests, or logs; authentication errors do not expose server response bodies.
- The default `data/` destination is ignored by Git; download success is not scientific calibration approval.
- [ESO authentication](https://eso.org/cms/eso-data/programmatic-access/authentication-and-authorisation.html) · [Raw calibration associations](https://www.eso.org/cms/application_support/calselectorInfo.html).

## Reduce and review

```sh
conda activate efospec
PYTHONPATH=src MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m efospec reduce-rapid ../pessto/2024-11-14 --output runs/2024-11-14
```

- Use a **fresh output directory**; existing runs are refused.
- One target: `--target SN2023xxj`; repeat the option for more targets.
- Automatic report: open `runs/2024-11-14/index.html`.
- Each exposure: spectrum, 2D trace, spatial profiles, PDF/JPG downloads.
- Repeated targets receive separate entries.
- Failures and skipped exposures remain recorded.
- Share/move the entire run directory; HTML links are relative and work offline.
- Plot regeneration reads products and native spectra from the selected run, including after a move.
- Historical manifest paths remain unchanged; raw inputs and external comparison spectra must still be available.
- Keep one reduction writer per run; raw inputs remain unchanged.

## Environment and report options

- Default plotting Python: current interpreter.
- Recommended runtime: `conda env create -f environment.yml`, then `conda activate efospec`.
- The dedicated environment includes plotting dependencies; no second Python is needed.
- Override: `--plot-python /path/to/python` or `EFOSPEC_PLOT_PYTHON`.
- The former `EPESSTO_PLOT_PYTHON` variable remains a fallback.
- Use `unset EFOSPEC_PLOT_PYTHON EPESSTO_PLOT_PYTHON` to select the dedicated runtime.
- Plot packages: `pip install -e '.[plots]'` in the chosen environment.
- System dependencies: LaTeX, `dvipng`, `type1cm`/`cm-super`.
- Extraction alone: `--skip-report`.
- Plotting failure: spectra survive; CLI returns nonzero; inspect `report-generation.log`.

```sh
PYTHONPATH=src python -m efospec report runs/2024-11-14
PYTHONPATH=src python -m efospec report runs/2024-11-14 --existing-plots
```

## Outputs

| Path inside a run | Contents |
| --- | --- |
| `products/` | Legacy `_f.fits` and two-column `_f.asci` |
| `native/` | PypeIt spec1d counts; saved detector, sky, trace, and selection arrays |
| `qa/`, `source/`, `run.json` | Per-exposure checks, executed source, input hashes and settings |
| `style-preview/` | Spectrum, 2D trace, spatial profiles, combined spectrum/trace; PDF/JPG |
| `index.html`, `report.json` | Fieldnotes report and completeness status |

- Flux FITS bands: **optimal, boxcar, sky, sigma** in physical cgs units.
- `VALID` extension: usable samples; invalid flux is NaN.
- Native wavelengths: vacuum; delivered wavelengths: air/topocentric.
- Resampling: bin-overlap flux conservation and diagonal variance propagation.
- No saved covariance; no flat/telluric corrections.
- Blue shading: global-sky input selection, before iterative rejection.
- Red shading: geometric boxcar aperture; not optimal-extraction weights.
- Spatial profiles omit two off-slit columns without sky models.

## Legacy comparisons and individual plots

```sh
python scripts/preview_spectrum_style.py --run runs/2024-11-14 --target SN2023xxj
```

- Omit `--target` to render every exposure.
- Matching legacy spectra are detected automatically; `validation.json` is optional.
- `--legacy DIR`: explicit comparison directory; `--no-legacy`: omit comparisons.
- Styling: 22 pt ticks; pastel-red PypeIt, black IRAF; SNR inside the spectrum.
- Plotting changes neither extraction nor calibration.
- The older `qa` command remains a demonstration-specific comparison report.

```sh
PYTHONPATH=src python -m efospec qa runs/2024-11-14 --legacy ../pessto/2024-11-14
```

- Standard checks: reduce separately with `--include-standards --target Feige110 --target L745a`.
- Add `--standards PATH` to `qa` for that standard-star run.
- Older runs without sky masks: recover once in the original PypeIt environment.

```sh
PYTHONPATH=src MPLBACKEND=Agg python -m efospec.sky_regions runs/2024-11-14
```

- Recovery must reproduce all recorded candidate positions before saving.
- It writes a sidecar; original spectra remain untouched.

## Inspect without reducing

```sh
PYTHONPATH=src python -m efospec inventory ../pessto/2024-11-14
PYTHONPATH=src python -m efospec native-readiness ../pessto/2024-11-14
PYTHONPATH=src python -m efospec plan ../pessto/2024-11-14
PYTHONPATH=src python -m efospec inspect-pypeit ../pessto/2024-11-14
PYTHONPATH=src python -m unittest discover -s tests -v
```

- `inventory`: read-only FITS headers, hashes, duplicates, conflicts, and missing inputs.
- Inspected detector geometry: 1030×1030; other geometries need review.
- Extension-only FITS readers remain future work.
- Inventory dependencies: Python 3.9+ and Astropy 6/7.
- `plan`: raw calibration associations; **does not build masters**.
- `inspect-pypeit`: metadata/raw-reader checks; **does not write a runnable .pypeit file**.
- Both accept `--profile rapid|full`, `--reference-root DIR`, and repeated `--arc FILE`.
- Off-night arcs require an explicit selection; processed masters cannot masquerade as raw arcs.
- Flat/bias/sensitivity overrides and persistent name reservations remain future work.
- Check `blockers`, `issues`, and readiness fields; planning success is not reduction readiness.
- Inventory exit codes: 0 completed, 1 unreadable files, 2 invalid input/setup.

## Scientific limits and repository layout

- Demonstrated: 13 science exposures on 2024-11-14, Gr11/Gr13, Free, 2×2.
- Raw standards exist; raw arcs/biases/flats are missing from this night.
- The archive bridge does not meet the requirement for IRAF-independent calibration.
- Eight historical aperture anchors; five nominal-position identities remain unverified.
- No full-calibration parity, native spec2d, resolution map, or Phase 3 certification.
- Red fringing, second-order contamination, and absolute flux need further validation.
- Legacy `trunk/` and existing NOT/PyRAF environments stay separate.
- Raw data and generated `runs/`, `outputs/`, and `data/` stay outside Git.
- Migration code and documentation are published in the `sPaMFouR/efospec` fork.
