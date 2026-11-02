# Recent-night validation

- Scope: two most recent complete EFOSC2 nights returned for the programme.
- Authenticated ESO downloads succeeded, including proprietary science frames.
- Raw data, target metadata, logs, plots, and products remain Git-ignored.
- Public record: aggregate outcomes and reproducible commands only.

## Initial archive-bridge baseline

| Observing night | Verified files | Products | Failed | Skipped |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-28 | 193 | 7 | 11 | 2 |
| 2026-10-29 | 203 | 5 | 10 | 3 |

- Files include acquisitions and associated raw calibrations from other dates.
- Reduction counts include science and standard exposures.
- Products: **7 science spectra and 5 standards**, all experimental.
- Stops: 11 sky-flexure failures, 3 source-selection failures, 7 unsupported-filter failures.
- Skips: 5 Gr16 exposures; the archive bridge enables Gr11/Gr13 Free only.
- The independent 6363 Å check passes for 8/12 products; 4 lack a passing check.
- Nominal-position target identities remain unverified.
- No scientific thresholds or target-selection rules were relaxed.

## Fixes and checks

- Inventory now records initial dome-flat template exposures as `flat_test`.
- These exposures no longer block preflight and cannot fill a master-flat group.
- Classification requires `DOME`, `CALIB`, `SPECTRUM`, the exact flat-template ID, and exposure number 1.
- Basis: observed template sequencing and the [ESO flat-template description](https://www.hq.eso.org/sci/facilities/lasilla/instruments/efosc/inst/CalSpecLongSlitFlats.html).
- Plot metadata now preserves decimal slit widths; repeated-target records remain distinct.
- Both regressions reproduced before their fixes; the updated suite passes **133 tests** locally.
- Local Python coverage: **90.41%**; remote badge metrics may differ.
- Both nightly reports contain all expected spectrum, trace, and spatial-profile figures.
- Download hashes/FITS checksums, product units/masks, raw immutability, and report links were checked.

## Reproduce locally

```sh
python -m efospec download 2026-10-28 --programme 117.29T8.002 --with-calibrations
python -m efospec download 2026-10-29 --programme 117.29T8.002 --with-calibrations
python -m efospec native-readiness data/2026-10-28
python -m efospec native-readiness data/2026-10-29
```

```sh
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m efospec reduce-rapid data/2026-10-28 \
  --output runs/2026-10-28 --include-standards
```

- Repeat with `2026-10-29`; use a fresh output directory for reruns.
- Reports: `runs/<date>/index.html`; current report status: `runs/<date>/report.json`.
- Private detailed checks: `runs/latest-nights-validation.json`.
- A failed exposure returns a nonzero run status while retaining completed products.
- `native-readiness` still returns nonzero: raw candidates exist, fully native
  science-to-flux delivery is not implemented and validated.

## Remaining acceptance work

- Validate experimental raw masters/wavelength fits and implement observed-standard sensitivity.
- Validate weak-sky/short-standard exposures against contemporary raw arcs.
- Verify source identity before replaying the new explicit recovery recipes.
- Validate additional grisms/filters before enabling them.
- The current successful runs execute no IRAF/PyRAF, but still import archived IRAF calibrations.

## Debugging follow-up — 1 November 2026

- Work in `EFOSpec`; the sibling `pessto` checkout is the preserved baseline.
- Reproduced all **11** original sky-flexure failures using unchanged raw FITS.
- Seven new synthetic checks failed before the fix; these cover displaced/broad
  lines and a displaced check line. The updated fitter passes them.
- Two demonstrated defects:
  - The peak used to initialise the fit could lie outside its ±50 Å centroid
    bounds; the exception was swallowed, producing an empty measurements list.
    Long Gr11 exposures triggered this even with a fitted green centroid near
    the boundary. The red centroid can also exceed the old bound.
  - Separate fixed windows mixed the 6300/6363 Å lines with their continua.
    This biased centroids/SNR and could prevent the check line from fitting.
- Fix: centre the green fitting window on the detected peak; use an explicit
  bounded ±80 Å search; model both red lines with independently free centroids,
  amplitudes, and widths. Reject boundary-limited/unconstrained fits.
- Unchanged scientific gates: both anchors need peak SNR >8 and agreement within
  3 Å. The 6363 Å check requires SNR >5 and a residual <3 Å.
- The check line does **not** set the shift or have a forced separation. It now
  shares a fitted continuum with 6300: their errors are correlated, and this is
  recorded in QA. It is not an entirely independent calibration validation.
- Synthetic offsets from −60 to +60 Å recover within 0.1 Å (1/30 test pixel).
  Disagreeing anchors, a single strong line, out-of-range shifts, and
  width-boundary fits still fail. A displaced 6363 line fails its check without
  dragging the shift to its position.

### Real-data outcome

| Night | Extracted products | Calibration failures | Source-selection failures | Unsupported setups |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-28 | 7 | 5 | 2 | 6 |
| 2026-10-29 | 8 | 2 | 2 | 6 |

- **15 products: 8 science + 7 standard candidates**, compared with 12 previously.
- Four previous sky failures pass the revised calibration: one science and two
  standards extract; the fourth reaches source selection and remains ambiguous.
- All 12 previously extracted exposures remain extractable.
- Seven remaining calibration failures: four lack a reliable >8-SNR red anchor;
  three have anchor disagreements of 3.15–3.57 Å. Do not lower the gate to pass them.
- Four source failures have multiple plausible nearby detections; the nominal
  pixel is not a verified target identity. Do not pick the brightest neighbour.
- Twelve unsupported exposures: seven Gr13/GG495 and five Gr16 configurations.
  All now use the same `unsupported_setup` classification; the filter cases
  were previously counted as errors. This reclassification is not a recovery.
- Ten of the 15 extracted products pass the 6363 check. Five do not have a
  passing check; retained products remain experimental. Previously reported
  check counts are not directly comparable because the old fit could accept a
  width pegged at its bound.

### Failure handling and evidence

- Per-exposure errors now save stage, exception type, code, action, setup,
  measurements, and a traceback under `errors/`.
- Source failures save candidate positions plus detector/sky/trace arrays in
  `native/*_selection_failed.npz`; the manifest records the raw/window origins.
  These are diagnostic files, not extracted or calibrated delivery products.
- `run.json` uses atomic replacement and starts with `execution_status=running`;
  completed runs distinguish `complete`, `partial`, and `failed` execution.
  Scientific status remains `EXPERIMENTAL` regardless of execution status.
- Unsupported/skipped requested exposures now give a nonzero CLI exit status,
  including runs with no products. Successful exposures survive other failures.
- Private detailed evidence: `runs/2026-11-01-debug/`.
- Fresh runs: `runs/2026-10-28-debug-20261101-final/` and
  `runs/2026-10-29-debug-20261101-final/`; originals are untouched.

```sh
MPLBACKEND=Agg OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python -m efospec reduce-rapid data/2026-10-29 \
  --output runs/2026-10-29-debug-new --include-standards
```

### Documentation findings and next scientific work

- [Installed PypeIt 1.14 EFOSC2 support](https://pypeit.readthedocs.io/en/1.14.0/spectrographs/ntt_efosc2.html)
  lists Gr5/Gr6; [current documentation](https://pypeit.readthedocs.io/en/latest/spectrographs/ntt_efosc2.html)
  lists Gr4/Gr5/Gr6. Neither establishes native Gr11/Gr13/Gr16 calibration.
  An upgrade alone does not complete our native pipeline. Both discuss EFOSC2
  overscan problems; enabling generic corrections without validating them is unsafe.
- [PypeIt wavelength calibration](https://pypeit.readthedocs.io/en/latest/calibrations/wave_calib.html):
  use contemporary raw arcs, physical vacuum line lists, and inspect fits across
  the spectrum; `pypeit_identify` provides a route to missing templates. Our
  archive bridge uses air Å, so conversion must occur exactly once at the engine boundary.
- [PypeIt flexure](https://pypeit.readthedocs.io/en/latest/calibrations/flexure.html):
  cross-correlation with resolution-matched sky spectra is a useful independent
  comparison to implement, with explicit search limits and QA. It is not used
  by this fix, and weak sky cannot establish a trustworthy correction by itself.
- [PypeIt manual extraction](https://pypeit.readthedocs.io/en/latest/manual.html):
  verify acquisition/trace coordinates and use explicit positions for ambiguous
  or faint targets. Failed-exposure replay was subsequently implemented; see
  [native calibration and recovery status](native-calibration.md#failed-source-recovery).
- [PypeIt sky subtraction](https://pypeit.readthedocs.io/en/latest/skysub.html) and
  [ESO FORS2 reduction discussions](https://support.eso.org/en-US/kb/articles/data-processing-of-fors2-data-faqs)
  explain the importance of object masks and appropriate sky regions. Use as
  methodological guidance, not as EFOSC2-specific parameter validation.
- [ESO EFOSC2 pipeline manual](https://ftp.eso.org/pub/dfs/pipelines/instruments/efosc/efosc-pipeline-manual-1.1.pdf)
  discusses wavelength-fit stability, sky alignment, and extended-source sky
  failures. More polynomial terms or a plausible extraction are not proof of accuracy.
- [PESSTO survey/reduction paper](https://doi.org/10.1051/0004-6361/201425237)
  distinguishes archive-based rapid spectra from full calibrated reductions.
  Complete the existing [native calibration acceptance work](native-calibration.md)
  before treating these products as fully reduced: bias/flat masters, raw arc/tilt
  solutions for each configuration, observed-standard sensitivity, independent
  sky checks, and comparison against reference spectra.

### Verification of this change

- Full suite: **148 passed**, **90.35%** Python coverage (85% required).
- All **396** downloaded FITS hashes match the download manifests.
- Both fresh nightly reports are complete; all 212 local links resolve.
- Saved reduction source snapshots match the implementation used for verification.
- No raw data or original reductions were overwritten; no commits or pushes made.

## Thorough native follow-up — 1 November 2026

- **19/19 distinct raw calibration groups now build:** 9 from 28 October and
  10 from 29 October, including Gr13/GG495 and Gr16/OG530 masters. This does
  not enable those setups in the archive-bridge science exporter.
- All 19 current solutions pass physical/coverage/held-out gates: 13–20 lines,
  arc RMS 0.005–0.174 pixel, maximum held-out RMS 0.222 pixel. These are internal
  arc-fit metrics, not total wavelength accuracy or independent confirmation.
- Fixed circular bias subtraction, false low-RMS line identifications,
  near-duplicate search hypotheses, and failure replay without an existing
  spectrum. Added explicit native-template reidentification with input hashes.
- **One initially successful Gr11/slit1.5 trial was wrong in the blue.** It
  assigned two ghost peaks despite plausible red sky checks. Its replacement
  restores the expected range; current validation rejects the older product.
  Never select an old calibration merely because its manifest says success.
- The final audit reapplied current gates and verified product/raw hashes for
  every selected group. Full details: local
  `runs/native-debug-20261101/final-audit.json`, including superseded paths and
  the authoritative source run for each group.

| Night | Raw groups built | Sky offsets measured | Sky checks failed | Gr16 red-sky check pending |
| --- | ---: | ---: | ---: | ---: |
| 2026-10-28 | 9/9 | 12 | 6 | 2 |
| 2026-10-29 | 10/10 | 11 | 4 | 3 |

- These are **native diagnostic counts for all 38 exposures**, not extracted
  spectra. The archive bridge still has 15 experimental extracted products.
- Measured native offsets span −7.29 to −3.54 Å. Sixteen of 23 measurements
  also pass the 6363 Å check; seven lack a passing check. The two red-line
  centroids share a fitted continuum and are not statistically independent.
- Ten native sky failures remain: seven weak/invalid 6300 Å anchors, three
  disagreements exceeding 3 Å. Eight are standard candidates, two science.
  Thresholds were retained; no unsupported correction was applied.
- All five Gr16 exposures are processed but explicitly unvalidated: they need
  suitable red sky lines/template checks, plus fringe validation.
- Four ambiguous source exposures have saved candidate recipes, detector/profile
  figures and acquisition-file associations. Their target identities are still
  unverified; no candidate was silently promoted to a supernova spectrum.
- Still required: native extraction with propagated masks/variance, sensitivity
  derived from independently identified observed standards, second-order and
  fringe assessment, and validation of full science/flux delivery.
- Verification: **156 tests passed**, **89.94% coverage**, all **396 raw FITS**
  hashes unchanged. Includes native raw-to-master integration, shifted-arc
  reidentification, false-range rejection, changed-master isolation, and
  failed-source manual replay. No environment changes, commits or pushes.

Authoritative local evidence (earlier trials are retained for diagnosis):

- 28 October: `runs/2026-10-28-native-calibrations-20261101-v2/`.
- 29 October: `runs/2026-10-29-native-calibrations-20261101-v2/`, with two failed
  groups replaced by `runs/2026-10-29-native-retry-20261101-v3/` and the false-blue
  group replaced by `runs/2026-10-29-native-corrected-20261101/`.
- Matching native-validation runs and the final audit record all 38 exposures
  exactly once, using the latest result for each corrected group.


## 1 November: C3 background review and native desktop editor

- Four dated QC packets now use the canonical house style, mandatory LaTeX, Hiroshige and paired PDF/300-dpi JPG exports. Report PNGs remain available.
- For the user's provisional C3 identification in SN2026aebl only, tested independent detector-row polynomial fits on raw x `[520,535)` and `[555,575)`. All 1,015 rows fit; 942 rows pass the existing wavelength validity range. Degree-1/2/3 median extracted counts are 1966.25/1471.52/1375.27 electrons per spectral row. Model-choice sensitivity remains unresolved; these are experimental boxcar counts without calibrated flux or validated host decomposition.
- Native PyQt6 editor delivered for this bounded workflow: candidate selection, raw-pixel aperture and background bands, fit-order selection, before/after profiles, recipe save/reload, extraction and cancellation. Actual macOS canvas interactions and exact preview/worker array agreement verified. Full desktop reduction application and Linux certification remain pending.
- Fixed a style-state leak that made PypeIt's own unescaped `#` labels fail in LaTeX after QC plotting. Added guards for invalid polynomial geometry, malformed sky JSON and unavailable output directories; originals remain unchanged.
- Final suite: **160 passed, 90.50% coverage** (`runs/polynomial-final-tests-v2.log`). Numerical tests include a known quadratic plus point source and background outlier, Monte Carlo variance propagation, invalid-row masking and immutable-recipe replay. All **396 raw FITS hashes** reverified unchanged; all QC links resolve.
- Details and launch/replay commands: [polynomial background workflow](polynomial-background.md). Native interaction evidence: `runs/background-gui-check/interactions-final/result.json`. C3 comparison: `runs/2026-10-28/QC/EFOSC.2026-10-29T05:12:40.988/C3-background-review.html`.


## 2 November: full rerun of both October epochs

All 396 downloaded raw files were inventoried and hash-verified. Every science and standard exposure was attempted in a fresh run; acquisition and calibration images retain their own roles. Existing native master groups were reused and reverified, not rebuilt.

| Observing night | Science + standards attempted | Archive spectra | Sky-flexure failures | Source-selection failures | Unsupported archive setups |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-10-28 | 20 | 7 | 5 | 2 | 6 |
| 2026-10-29 | 18 | 8 | 2 | 2 | 6 |
| Total | 38 | 15 | 7 | 4 | 12 |

- Unsupported: five Gr16/OG530 and seven Gr13/GG495 exposures. These are explicit skips, not successful reductions.
- Native diagnostics independently processed the same 38 exposures with 19 verified calibration groups: 23 measured sky offsets, 10 failed sky checks, five Gr16 exposures still lacking a validated red-sky check. These are diagnostic results, not native extracted spectra.
- Both Fieldnotes reports completed, including house-style figures. Fresh QC packets and 11 unverified candidate trials completed for the four ambiguous exposures.
- Replayed the user-scoped SN2026aebl C3 quadratic recipe on the new run only after verifying identical raw/calibration hashes and detector data, wavelength map and traces. Counts, variances, masks and validity reproduce the earlier experiment to an absolute tolerance of 1e-9. This additional count product is not included in the 15 archive flux products and does not establish validated host subtraction.
- All 396 raw files, 19 native master groups and the new parent-run files remained unchanged during QC/recovery. The original reductions were preserved.
- Local verification: **160 tests passed; 90.50% coverage; wheel build passed.** Logs: `runs/pre-push-tests-20261102.log` and `runs/pre-push-build-20261102.log`.

Local reports and machine-readable evidence (generated data remain outside Git):

- `runs/batch-20261102/index.html`, `summary.json`, `exposures.csv`, `verification.log`.
- `runs/2026-10-28/reduction-20261102/index.html` and `runs/2026-10-29/reduction-20261102/index.html`; each run contains `QC/`, `products/`, saved errors and source snapshots.
- `runs/2026-10-28/native-validation-20261102/validation.json` and `runs/2026-10-29/native-validation-20261102/validation.json`.
- Batch orchestration, selected-master provenance and recovery comparisons are retained under `runs/batch-20261102/`.

Reproduction uses the current checkout and existing pinned environment:

```sh
efospec reduce-rapid data/2026-10-28 --output runs/2026-10-28/new-reduction --include-standards
efospec reduce-rapid data/2026-10-29 --output runs/2026-10-29/new-reduction --include-standards
```

Each output directory must be fresh. The batch is completed with explicit failures; full native calibration-to-flux delivery, unsupported-setup validation and remaining source/background decisions are still outstanding.


## 2 November: organize the 2026-10-28 artifacts

- Consolidated 23 older entries into the date's `archive/` and `calibrations/`; the current `nightly/` revision and reviewed `QC/` products stayed in place. `runs/2026-10-28/index.html` and its README now provide one starting point. The original reduction is under `archive/initial-reduction/`.
- Preserved all 1,825 pre-existing files. Scientific data and all saved manifests/recipes are byte-for-byte unchanged. Repaired external links in two moved HTML pages and retained hash-verified copies of their originals. Eight compatibility links preserve older paths used by saved provenance; no files were deleted and raw data were not moved.
- Verified all 193 raw hashes for this epoch, all 19 native calibration groups referenced by the shared audit, 619 local report links, loading the archived initial reduction, and exact numerical replay of both retained C3 recipes. The current nightly revision is unchanged; no broken report links remain in the checked date tree.
- Relocation map, before/after hashes, original HTML backups and verification: `runs/2026-10-28/archive/cleanup-20261102/`. The folder-layout policy lives in [the epoch workflow](epoch-workflow.md).

## 2 November: portable epoch Fieldnotes

- Replaced the date's link directory with a single document: observing log, spectra, issues, source QC, background experiments, calibrations, archive and run record. Embedded 31 existing house-style figure previews and product/log downloads; no sibling pages or network access are required.
- Verified offline navigation, figure enlargement, byte-identical FITS downloads and mobile layout. The actual 2026-10-28 page loaded all figures without browser errors. All 193 raw hashes and 223 checked science artifacts were unchanged.
- Integrated the dated workflow with the newer GitHub desktop/native changes. Full suite: 217 passed, 90.40% coverage; final focused checks: 21 passed, including the additional exposure-bound background-revision test. Wheel build passed. Evidence is retained in the current nightly revision's `fieldnotes-verification.json` and dated validation logs.
