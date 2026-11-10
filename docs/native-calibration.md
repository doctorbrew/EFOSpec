# Native calibration: inputs and status

- **10 November engine migration:** `efospec` now uses PypeIt 3.0.0. New raw Gr11/Gr13 calibration and flexure benchmarks are documented in [the migration record](pypeit3-migration-2026-11-10.md). Historical 1.14 calibration files require the preserved runtime; rebuild from raw for 3.0. Science wavelength validation remains separate.

- **8 November debugging:** [flux-calibration audit, Gr16 review counts, background trials and held-out standard checks](reduction-debug-2026-11-08.md). These new diagnostics do not replace the selected nightly products.
- **Required destination:** no IRAF/PyRAF execution or IRAF-derived calibrations.
- **Current runner:** `reduce-rapid` still uses archived IRAF line IDs and sensitivity.
- **Native reduction:** experimental raw-only runner, demonstrated on one Gr13 exposure; [usage and scientific limits](native-raw-run.md).
- **Scope:** EFOSC2 optical spectroscopy; start with Gr13/Gr11.

## What the local folders contain

Paths below are relative to the parent `pessto/` workspace.

| Location | Contents | Native calibration input? |
| --- | --- | --- |
| `database/ap*`, `2024-11-14/database/ap*` | IRAF aperture, trace, background settings | Comparison only |
| `database/idarc*`, `2024-11-14/database/idarc*` | IRAF identified lines and wavelength fits | Comparison only |
| `database/fcarc*`, `2024-11-14/database/fcarc*` | IRAF coordinate transformations | Comparison only |
| `2024-11-14/arc_20120825_Gr13_Free_slit1.0_56442_1.fits` | Processed arc; observed 2012-08-26; `FILETYPE=22104` | No |
| `EFOSpec/trunk/src/ntt/archive/efosc/` | Older processed arcs, master biases/flats and responses | Comparison only |
| `2024-11-14/EFOSC*.fits` | Raw science, standards, and imaging | Science/standards: yes |

- **Raw standards exist:** four Feige110 and four L745a exposures.
- **Setups:** Gr11/Free, Gr13/Free, Gr16/OG530; slit widths vary.
- **Missing:** raw arc, bias, and flat exposures in the inspected night.
- **Also checked:** `Anna_20241114.zip`, `Avinash_2024-11-14.zip`, and the installation-test `.tgz`.
- The archives contain no additional raw arcs, biases, or flats.
- `DATE-OBS` falls on 15 November UTC for this 14 November observing night.
- A `DPR TYPE=WAVE` header alone does not make an arc raw; inspect processing markers too.

## Raw Gr13 inputs now retrieved

- ESO CalSelector returned raw associations for SN2023xxj, exposure `EFOSC.2024-11-15T07:37:44.091`.
- Downloaded locally to **`data/2024-11-14-eso-calibrations/`** inside `EFOSpec`.
- Contents: **1 arc, 7 flats, 10 biases**, with original `.fits.Z` downloads retained.
- Arc: `EFOSC.2024-11-15T09:00:31.548.fits`.
- Arc/flats: Gr13, Free, slit1.0; all frames use 2×2 binning and `fastL` readout.
- Biases: **7 November**, eight days before the science exposure; age requires scientific review.
- ESO association: `complete=true`, **`certified=false`**; this is not a quality approval.
- Our check finds complete raw candidates for SN2023xxj plus the existing Gr13/slit1.0 standards.
- PypeIt's raw reader opens all 18 frames with the expected 1030×1030 geometry and detector metadata.
- These 2024 inputs are catalogued; the new raw-only end-to-end demonstration uses October 2026 data.
- This retrieval covers one configuration; Gr11 and other slit/filter combinations still need their inputs.
- [Input identifiers, download URLs, and SHA-256](calibration-inputs/2024-11-14-gr13.csv).
- [ESO raw association request](https://archive.eso.org/datalink/links?ID=ivo%3A%2F%2Feso.org%2FID%3FEFOSC.2024-11-15T07%3A37%3A44.091&eso_download=calSelector_raw2raw).
- [ESO retrieval documentation](https://www.eso.org/cms/application_support/calselectorInfo.html).

Raw files remain ignored by Git; the public repository records their retrieval details.

## Recent nights with complete raw candidates

- Authenticated retrieval: **2026-10-28 and 2026-10-29**, including associated raw calibrations.
- Local directories: `data/2026-10-28/` and `data/2026-10-29/` inside EFOSpec.
- Preflight finds arc/bias/flat candidates for all 38 science/standard exposures.
- Same-night standard candidates are available for all 15 science exposures.
- Initial dome-flat test exposures are recorded separately and excluded from master-flat candidates.
- Candidate availability does not validate standard identities, calibration quality, or native execution.
- Proprietary identifiers and products remain local; [aggregate validation](validation-2026-10.md).

## Check another directory

```sh
python -m efospec native-readiness /path/to/night /path/to/raw-calibrations
```

- Reads FITS headers and hashes; leaves files unchanged.
- Checks raw candidates against detector, grism, filter, slit, and night.
- Requires at least three biases/flats per selected group.
- Ignores processed products; never opens IRAF databases or reference catalogues.
- Reports missing, ambiguous, and incompatible selections.
- Standard candidates still need independent identity/reference verification.
- Returns **1** while native execution or required calibration inputs are missing.
- `raw_candidates_complete` means candidate availability, not scientific validation.

## Work required before native acceptance

- Check raw-calibration coverage for each additional night and configuration.
- Match binning/readout and grism/filter/slit; retain acquisition metadata.
- Validate the experimental raw bias/flat masters, slit traces and tilt maps.
- Review raw-lamp identifications against physical line lists and independent arcs.
- Validate Gr11/Gr13 solutions with held-out arc and night-sky lines.
- Match observed standards to independently sourced physical flux references.
- Derive sensitivity from those observations; validate extinction and slit losses.
- Preserve legacy delivery names, wavelength conventions, units, and uncertainty bands.
- Test raw-to-delivery execution with the entire legacy calibration directory unavailable.
- Compare the resulting products with IRAF only after native processing succeeds.

Full implementation remains tracked in [T1–T5](roadmap/pypeit-migration/tasks.md).

## Native calibration execution — 1 November 2026

- **Implemented experimentally:** `calibrate-native` builds bias, traced slits,
  processed raw arcs, wavelength fits, tilt maps, and pixel/illumination flats
  through the pinned PypeIt engine. It uses no legacy reference directory.
- **Separate diagnostic command:** `validate-native` applies these masters to raw
  exposures and measures sky offsets. It does not export science spectra or
  apply an unvalidated flexure correction.
- **Still absent:** a validated native science-to-flux delivery path, independently
  derived observed-standard sensitivity, second-order correction, and tellurics.
  `native_execution_implemented` and `reduction_ready` therefore remain false;
  `native_calibration_execution_implemented` identifies the new bounded capability.

```sh
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m efospec calibrate-native data/2026-10-29 \
  --output runs/2026-10-29-native-calibrations
python -m efospec validate-native runs/2026-10-29-native-calibrations \
  --output runs/2026-10-29-native-validation
```

- Both commands require fresh output directories. `--grism Gr13` limits a
  calibration experiment; repeat for multiple grisms.
- `--group GROUP_ID` limits a retry to named groups. Optional `--template-map`
  takes a JSON object mapping group IDs to successful native group directories.
  Templates must match the entire setup and pass current physical gates; their
  masters and raw inputs are hash-checked. PypeIt reidentifies and refits the new
  raw peaks, using only the template's accepted line IDs. It never copies a
  wavelength solution or silently selects a fallback. See
  [PypeIt's reidentification algorithm](https://pypeit.readthedocs.io/en/latest/calibrations/wave_calib.html#reidentify).
- Existing raw associations, detector modes, filters, slit widths and hashes
  determine groups. No silently substituted arc or flat group is allowed.
- Each group saves associations, effective parameters, physical line table,
  calibration FITS, arc-fit QA, execution log and `calibration.json`.
- Native validation rebuilds its wavelength map from hash-verified masters.
  It reapplies current wavelength gates to older successful groups. Missing,
  changed or invalid masters fail their group while other groups continue.
  A successful calibration command is **not** a scientific acceptance flag.
- Gr16 does not include 5577 Å: its independent red-sky diagnostic is pending,
  explicitly reported as `processed_unvalidated`.

### Causes found by executing the native path

- **Circular bias dependency:** the full profile enabled subtraction of a bias
  from the bias frames used to build that same master. Fixed by disabling
  `use_biasimage` for bias frames; verified with actual PypeIt image processing.
- **False arc solutions:** unrestricted blind matching reported a small RMS for
  a negative central wavelength. Restricting the search alone still admitted
  a physically wrong solution. A red-line fit also misidentified a blue ghost.
- Native fitting now requires expected grism range/dispersion, monotonicity,
  at least 10 accepted lines, at least two per spectral third, sufficient span,
  RMS <=0.25 pixel, and interior leave-one-out RMS <=0.25/max <=0.5 pixel.
  Competing accepted identifications remain blocked for review.
- **Further false-positive discovered:** a Gr11/slit1.5 solution misidentified
  two blue peaks despite small fit/held-out residuals and plausible red sky
  checks. The initial ±300 Å endpoint gate admitted it. The acceptance bound
  is now conservatively ±100 Å; the wider hypothesis search remains separate.
  This is our experimental acceptance policy, not an ESO accuracy guarantee.
- **Search-budget defect:** near-duplicate affine guesses occupied the top 300
  candidates and excluded distinct line assignments. Deduplicating initial
  assignments recovered the failed Gr11 raw arc. That corrected same-setup
  solution then seeds a fresh fit for the affected neighbouring group.
  Early trial products from the false solution are superseded; they must not
  be used for science. Current validation rejects them.
- The search uses the instrument range/dispersion from
  [ESO's grism table](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/inst/Efosc2Grisms.html)
  and identifies only physical HeI/ArI lines selected using Table 17 of the
  [EFOSC2 manual](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/doc/manual/EFOSC2manual_v4.2.pdf).
  Rounded air values select entries in PypeIt's NIST lists; all actual native
  fitting uses the latter's **vacuum Å** values. Saved ECSV tables preserve them.
- Detector-end extrapolation is not validated: each solution records its
  accepted reference-line bracket. Future delivery must mask outside it.
- The first tested Gr13 raw fit has 18 accepted lines, RMS 0.034 pixel and
  held-out RMS 0.045 pixel. This establishes an arc fit, not science flux accuracy.
- New synthetic integration coverage builds the complete set of native masters
  from raw bias/flat/arc frames, checks the known wavelength map, and verifies
  raw-file immutability. Another test rejects low-RMS impossible solutions.

### Failed-source recovery

```sh
python -m efospec prepare-recovery runs/2026-10-29 \
  --raw EFOSC.example.fits --output runs/2026-10-29-source-recipes
python -m efospec reextract runs/2026-10-29 \
  --failed-raw EFOSC.example.fits \
  --recipe runs/2026-10-29-source-recipes/candidate-1.json \
  --output runs/2026-10-29-source-revision
```

- Replace the example basename with an actual failed exposure. The first command
  generates **position hypotheses**, not approved target identities. Inspect
  acquisition/finding-chart evidence, widths, and sky regions before replay.
- Recovery now works without an existing successful product. It retains the
  archive-bridge calibration used for that exposure; it is not native calibration.
- Requires the latest failure records: raw/arc/line-ID/sensitivity/extinction
  hashes plus saved detector and wavelength arrays. Older failures need rerunning.
- Validates raw pixels against the saved image and recomputes the recorded
  wavelength map; stale recipes and modified inputs are rejected.
- Fresh revision directories preserve the parent run. Separate failure files
  prevent repeated-target exposures from overwriting each other's diagnostics.
- A synthetic ambiguous two-source exposure exercises recipe creation, explicit
  recovery of the intended source, immutability, and tamper rejection end to end.
- The four real failures now have candidate recipes and detector/profile plots
  under the local `runs/native-debug-20261101/recovery-*` evidence directories.
  Acquisition images were found, but their headers lack a celestial WCS.
  Nominal telescope coordinates do not identify a trace. These four targets
  still require verified positions or astrometrically registered finding charts.

### Dated QC packets and candidate trial extraction

```sh
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m efospec recovery-qc /path/to/current-failed-run \
  --raw EFOSC.example.fits \
  --output runs/2026-10-29/QC/EFOSC.example --test-recipes
```

- Requires a fresh exposure subfolder and current failure records. Creates
  raw/window images, saved trace overlays, spatial profiles, same-OB acquisition
  images, recipes, a read-only `index.html`, and a blank target-selection CSV.
- All coordinates are zero-based raw image pixels; plotted images retain their
  original orientation. Spectral and acquisition coordinates are not registered.
- Recipe anchors use each saved trace at the middle spectral row. Trial labels
  are neutral `Candidate-N-UNVERIFIED` names; `ORIGOBJ` preserves the exposure
  label. No candidate is automatically accepted as the astrophysical target.
- `--test-recipes` extracts each candidate separately in `trials/`, checks finite
  valid samples and positive inverse variance, and records fitted trace drift.
  Drift exceeding half the initial FWHM is flagged for inspection. Successful
  execution is not validation of source identity, aperture, host deblending,
  background selection or flux calibration.
- Trials deliberately replay the saved archive bridge; they do not apply the
  experimental native masters. Existing science products and raw files stay intact.
- Local packets are available in `runs/2026-10-28/QC/` and
  `runs/2026-10-29/QC/`, with two ambiguous exposures per night.
