# ePESSTO+ migration workspace

This fork is the development home for migrating **EFOSC2 optical spectroscopy**
from IRAF/PyRAF to PypeIt. SOFI spectroscopy is a later phase. The original
pipeline and its calibration library remain under `trunk/`.

**Current status: experimental rapid reductions demonstrated on the 2024-11-14
EFOSC2 night.** All 13 Gr11/Gr13 science exposures now have native PypeIt
extractions and legacy-named flux FITS/ASCII products. The existing `pypeit`
Conda environment (PypeIt 1.14.0) is the development/test environment.
The demonstration imports archived IRAF arc identifications and sensitivity;
it does not yet generate native calibration masters or establish full-profile
parity. Legacy commands still run the legacy pipeline.

- [Migration design and scientific decisions](docs/roadmap/pypeit-migration/README.md)
- [Legacy compatibility contracts](docs/legacy-spectroscopy-contract.md)
- [Implementation tasks and acceptance gates](docs/roadmap/pypeit-migration/tasks.md)
- [Inspection evidence and local validation](docs/roadmap/pypeit-migration/evidence.md)
- [Pipeline stages: PypeIt and the calibration bridge](docs/pipeline-stages.md)

## Reproduce the demonstrated rapid reduction

From this repository root, using a fresh output directory:

```sh
conda activate pypeit
export EPESSTO_PLOT_PYTHON=/Users/avinash/Softwares/miniconda3/bin/python
PYTHONPATH=src MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m epessto_plus reduce-rapid ../2024-11-14 --output runs/my-night
PYTHONPATH=src MPLBACKEND=Agg python -m epessto_plus qa runs/my-night --legacy ../2024-11-14
```

`--target SN2023xxj` selects one target; repeated `--target` options select more.
For standard checks, use a separate output directory with `--include-standards
--target Feige110 --target L745a`. Pass that directory to `qa --standards`.
The QA figures currently demonstrate this specific night and SN2023xxj.

`reduce-rapid` automatically generates `runs/my-night/index.html`: an offline
Fieldnotes page with the exposure table first, then each target's spectrum,
standalone 2D trace and spatial profiles side by side. There is no source-selection
column; unverified identities remain noted with the affected target's figures.
Click any image to enlarge it, or download its PDF/JPG. All successful exposures,
including repeated targets, are shown; failed/skipped reductions remain recorded.
Keep the run directory together when moving or sharing the page. No server or
network connection is needed.

The environment variable above uses the existing local plotting environment;
`--plot-python /path/to/python` overrides it. Without either, plotting uses the
reduction Python, which needs the `plots` extra (`pip install -e '.[plots]'`) and
LaTeX (`latex`, `dvipng`, `type1cm`/`cm-super`). Nothing is installed automatically.
Use `--skip-report` for extraction alone. A plotting failure leaves the spectra
intact, writes an incomplete page and `report-generation.log`, and returns a
nonzero CLI status. After fixing the plotting environment, rebuild without
repeating extraction:

```sh
PYTHONPATH=src python -m epessto_plus report runs/my-night --plot-python "$EPESSTO_PLOT_PYTHON"
# Rebuild only HTML from existing plots (also works after moving the run):
PYTHONPATH=src python -m epessto_plus report runs/my-night --existing-plots
```

The completed local run is `runs/2024-11-14-pypeit-rapid/`, with:

- `products/`: historical `_f.fits` and two-column `_f.asci` filenames; FITS
  primary bands are optimal flux, boxcar flux, sky and sigma in physical cgs.
  A `VALID` extension marks usable samples; invalid flux is NaN.
- `native/`: re-opened PypeIt spec1d files (electrons, vacuum wavelengths),
  plus detector data, sky/object models, traces, masks and wavelength arrays.
- `run.json`, `qa/`, `source/`: raw/reference hashes, actual engine versions,
  calibration fits, sky shifts, target choices, failures and executed source.
- `night-overview`, `SN2023xxj-validation`, `standard-validation`: PNG/PDF
  figures, plus numerical comparisons in `validation.json`.
- `index.html`, `report.json`, `style-preview/`: automatic Fieldnotes report,
  report completeness and the house-style PDF/JPG figures.

The bridge supports the inspected 2×2 Gr11/Gr13 Free-filter mode. It uses the
legacy rapid trim and no bias/flat/overscan/dark correction, fits the archived
air-wavelength IDs, measures a sky offset, converts to vacuum for native
PypeIt tracing/sky/optimal extraction, then exports topocentric air wavelengths.
The old logarithmic sensitivity and rapid La Silla extinction curve are applied
with explicit gain, exposure and dispersion factors. Resampling conserves flux
and propagates diagonal variance; correlations are not exported.

Eight science sources use historical aperture geometry; five use the nominal
acquisition position and remain **unverified target associations**. These outputs
are `EXPERIMENTAL`/`Rapid`. Telluric absorption and red fringing remain, and red
second-order correction is unvalidated. No Phase 3 certification, native spec2d
product, resolution map, contemporary calibration generation, or full migration
is claimed. Existing runs are refused instead of overwritten; use one writer
per fresh output directory. Input data and `trunk/` remain unchanged.

## Use the existing PypeIt environment

The house-style spectrum preview can be rendered separately using the existing
base Conda Python, which already includes SciencePlots and pypalettes:

```sh
/Users/avinash/Softwares/miniconda3/bin/python scripts/preview_spectrum_style.py --run runs/2024-11-14-pypeit-rapid --target SN2023xxj
```

Omit `--target` to render every exposure in a run. A legacy spectrum and
`validation.json` are optional: comparisons are detected from saved QA or the
raw-data directory, and an IRAF legend entry appears only when a matching
legacy file exists. `--legacy DIR` supplies comparisons explicitly; `--no-legacy`
produces PypeIt-only spectra. Each exposure gets a standalone spectrum and a
combined spectrum/trace figure (`FitSpectrumTrace_*`), with 22 pt tick labels,
pastel xkcd:red for PypeIt and xkcd:black for IRAF. The trace panel highlights
the selected global-sky input pixels in blue, with air-wavelength guides at
5577.338, 6300.304 and 6363.776 Å. Its wavelength grid is rectified for display;
the extracted flux arrays remain unchanged. The binary sky mask is resampled
with nearest-neighbour selection, never smoothed into artificial sky regions.
The median SNR appears inside the spectrum at the bottom centre; no flux-ratio
footer is drawn. Both combined panels show wavelength tick labels, and the
sky-line guides have no text tags.

A third figure (`FitSpatialProfile_*`) shows spatial sums of sky-subtracted
electrons in three equal wavelength bins, using native on-slit pixels without
resampling or normalization. The two off-slit boundary columns, which have no
sky model, are excluded and recorded in the plot metadata. The target trace
centre, geometric boxcar aperture (from the
native `BOX_RADIUS` and `TRACE_SPAT`), and sky-background selection are marked.
Shading opacity follows the selection fraction within each wavelength bin,
retaining trace curvature and changes in the background mask. The boxcar region
is not the weighting function of the optimal extraction.
The webpage uses a standalone 2D figure (`FitTrace_*`) beside the spectrum and
spatial profile; the combined figure is also retained. Re-rendering plots updates
the Fieldnotes page automatically.

New rapid runs retain the background selection directly in `*_images.npz`.
For older runs, recover it once using the original PypeIt environment:

```sh
PYTHONPATH=src MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  /Users/avinash/Softwares/miniconda3/envs/pypeit/bin/python -m epessto_plus.sky_regions runs/2024-11-14-pypeit-rapid
```

Replay must reproduce every recorded object position before writing the sky
selection sidecar. Shading represents the global-sky input selection before
iterative rejection; local extraction subsequently fits object and sky jointly.
It is not an invented pair of fixed background windows. Each plot uses its own
wavelength and flux ranges and saves PDF/JPG files under `style-preview/`.
The older comparison `qa` command retains its original report defaults; the
automatic Fieldnotes page uses these house-style figures.

From this repository root:

```sh
conda activate pypeit
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m epessto_plus plan ../pessto_test ../2024-11-14
PYTHONPATH=src python -m epessto_plus inspect-pypeit ../pessto_test ../2024-11-14
```

Both new commands accept `--profile full` (default) or `--profile rapid`.
Use `--arc /path/to/raw-arc.fits` for an explicit arc selection, repeatable for
multiple setups. Supplied arcs must be raw, physically compatible files;
processed IRAF masters are rejected. `--reference-root` defaults to
`trunk/src/ntt` and identifies the preserved catalogue/extinction references.

`plan` writes deterministic JSON with standard catalogue matches, selected
raw calibration groups, hashes, reasons, rejected candidates and blockers.
It does not build or import masters. Full planning uses same-night arcs/flats/
standards; raw bias groups are selected by compatible mode and nearest time.
Off-night arcs require an explicit selection. The separate `reduce-rapid` command
implements the demonstrated archive bridge; this raw planner does not substitute
archive masters. Explicit flat/bias/sensitivity overrides and persistent name
reservations remain future work. This is not full legacy parity.

`inspect-pypeit` exercises the installed engine's metadata, configuration grouping
and raw pixel reader through a custom spectrograph instance. It verifies source
hashes, uses catalogue-verified standard identities, groups by filter/readout,
uses detector-header gain/noise, and exposes effective processing parameters.
It emits a JSON inspection report, **not a runnable `.pypeit` file**. Calibration
groups, missing grism templates, flats and export still need validation.
The adapter currently requires the tested PypeIt 1.14.0 version; another version
requires explicit testing. No environment upgrade or site-packages patch is used.

## Inventory without PypeIt

Use Python 3.9+ with Astropy 6 or 7. From this repository root:

```sh
PYTHONPATH=src python3 -m epessto_plus inventory ../pessto_test ../2024-11-14
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The inventory recursively reads FITS headers, records SHA-256 digests, reports
duplicate content and conflicting archive identities, and prints JSON. It makes
no changes to the input files. It recognizes the inspected 1030×1030 EFOSC2
detector mode; other geometries require review. Standard candidates still need
catalogue verification. It does not perform calibration association or a full
header-validity check. FITS data stored only in extensions need a later reader.

To save a local report:

```sh
mkdir -p outputs
PYTHONPATH=src python3 -m epessto_plus inventory ../pessto_test ../2024-11-14 > outputs/local-inventory.json
```

Exit status 0 means the requested inspection/plan completed, not that reduction
is ready. Inventory status 1 reports unreadable individual files; status 2 means
invalid input or an unusable setup request. Check `blockers`, `issues`,
`associations_complete`, and `reduction_ready`; readiness remains false.

For a portable installation in a separate environment with a current pip
(packaging verified with pip 24.0), use `python -m pip install -e .`, then
`epessto-plus inventory /path/to/raw`. This installs only
the new package; `trunk/setup.py` remains the independent legacy installer.
Use the existing `pypeit` environment for native tests. A newer engine may be
evaluated later if a demonstrated requirement warrants it; it is not a
prerequisite for this work. Keep the working NOT/PyRAF environments unchanged.

Raw science inputs, local reports, and run products belong outside Git or in
ignored `data/`, `outputs/`, and `runs/` directories. Existing upstream calibration
files remain versioned. The public fork initially contains upstream history;
the migration additions in this checkout have not been committed or pushed.
