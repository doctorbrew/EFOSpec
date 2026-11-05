# Integrated reduction checks

Implemented in the dated workflow and `reduce-rapid`. Scientific products remain
experimental. Review evidence is retained even when extraction cannot proceed.

## Methodology

1. Inventory and hash the raw exposures. Write `setup-checks.json` with actual
   arc, bias, flat and standard-candidate associations for every configuration.
   Candidate availability does not enable an unsupported archive setup.
2. Fit the archived wavelength map. Save the sampled sky spectrum and the
   green/red line models before evaluating the existing flexure gates.
3. Compare the same sky with PypeIt 1.14's `spec_flex_shift`, using its Paranal
   sky template. Convert air to vacuum once, resample to a uniform vacuum grid,
   measure a pixel shift, then convert the diagnostic offset back to air Å.
   Record the template-array hash, smoothing inputs, search bound and result.
4. Apply only the accepted line-based correction. Both 5577/6300 anchors still
   require valid fits, peak S/N >8 and agreement within 3 Å. The 6363 check is
   recorded separately. Template correlation does not override a failed gate;
   it uses the same sky data and is not independent validation.
5. Prefer an explicitly reviewed source; otherwise choose the strongest positive
   peak within 15 spatial pixels of the expected central position, retaining
   detection-S/N checks. This selects extraction geometry, not target identity.
   Perform the bounded, two-sided PypeIt background fit and extraction. Tied or
   absent central sources and failed background support retain candidate geometry,
   diagnostic images and acquisition/candidate QC packets for review.
6. Write native `spec1d` and `spec2d` diagnostics for successful extractions;
   source-selection/background failures also retain `spec2d` windows with no object model.
   Deliver the usual flux products only when their reduction succeeds.
7. Render wavelength-fit/correlation figures and source QC into the dated
   ePESSTO+ report. Save new recipes and outputs in fresh revisions.

## Contemporary raw-calibration checks in the same run

```sh
python scripts/reduce_epoch.py 2026-10-28 \
  --native-calibrations runs/2026-10-28/calibrations/selected-20261102
```

- The calibration run is explicitly selected. Associated exposures must belong
  to the requested observing night and match its raw hashes. Native validation
  verifies master hashes and reapplies current wavelength-solution gates.
- `native-validation/` records fresh raw processing and sky comparisons against
  those masters. These checks do not substitute a native wavelength map or
  response into archive-calibrated spectra.
- Gr16 now receives a PypeIt correlation over 6500–8500 air Å. It remains
  `processed_unvalidated`: a correlation measurement alone does not establish
  a validated red-line correction, response or fringe treatment.
- Optical comparison uses 5300–6500 air Å. Correlation peaks at the search
  boundary, non-maximal fits, insufficient coverage and missing templates are
  recorded as unavailable, never as a measured zero shift.
- Native check failures make the nightly workflow partial while retaining the
  archive products and the report. Only the specified night is processed.

## Inspect and replay

- `reduction/checks/EXPOSURE/check.json`: input/calibration identity, fit gates,
  line measurements, comparison result and the correction actually applied.
- `curves.npz`: sky samples, fitted models and the correlation-peak samples.
  Plotting verifies its hash. PDF and 300-dpi JPG are the canonical figures;
  PNG previews are embedded in the portable nightly report.
- `reduction/native/spec2d_*.fits`: real image, input/model inverse variance,
  masks, sky/object models and the vacuum wavelength map. A failed selection
  has `QCSTAGE=source_selection_failed` and `OBJMODEL=False`; it is not an
  extracted spectrum. Pixel coordinates are local to the extraction window;
  successful exports also record `RAWX0/RAWY0`.
  Rapid-path slit edges describe the extraction-window boundaries, not a new
  measurement of the full detector slit. Early failed checks can have a zero
  placeholder sky model; their stage and saved mask explain what was fitted.
- `pypeit_show_2dspec PATH` can inspect these files with Ginga. A matching
  successful `spec1d` supplies the trace overlay. For failed exposures, use
  EFOSpec's saved candidate overlays and Source review tab.
- `pypeit_chk_wavecalib WAVE_CALIB_FILE` and `pypeit_identify ARC_FILE SLITS_FILE`
  inspect the selected native calibrations. These require actual PypeIt master
  files; NPZ arrays are not substitutes. The standard upstream sky-region GUI
  also expects its own reduction metadata; our supported recipe editor remains
  the EFOSpec desktop application.

Target identification, background selection, wavelength validation and flux
validation are separate decisions. Numerical extraction success cannot identify
SN2026ayt or validate SN/host separation. The provisional C3 experiment remains
specific to SN2026aebl.

## Gr16/OG530 delivery requirements

- AT2026twd's Gr11/Free exposure is supported by the rapid archive path. Its
  separate Gr16/OG530, slit1.5, 2x2 exposure is explicitly unsupported there.
- For the Gr16 exposure, the current inventory supplies one matching arc, ten
  bias candidates, three flats and a same-setup VMa2 standard candidate. Native
  diagnostic masters already exist; lack of raw files is not the primary blocker.
- Extend the paired native extraction/flux path beyond its current Gr11/Gr13
  gate, with verified Gr16 geometry, wavelength mapping, variance and export.
- Establish an independently checked red-sky flexure correction. The present
  5577/6300 method cannot apply because 5577 Angstroms is outside this setup;
  the existing red-template correlation is diagnostic only.
- Identify the observed standard against a physical reference and fit a supported
  Gr16/OG530 sensitivity curve. VMa2 currently lacks a registered native reference;
  the candidate's presence does not establish a usable response.
- Validate red response coverage, fringing, telluric regions and uncertainty
  transfer before approving the spectrum for quantitative analysis. Keep failed
  and unvalidated checks visible instead of enabling a setup by filename alone.

References: [PypeIt 1.14 2D diagnostics](https://pypeit.readthedocs.io/en/1.14.0/out_spec2D.html),
[sky regions](https://pypeit.readthedocs.io/en/1.14.0/skysub.html), and the installed
PypeIt 1.14 `core/flexure.py` implementation. EFOSpec deliberately leaves
PypeIt's extraction-time correction disabled to prevent double correction.

## Summed spatial-profile diagnostics

- With a fitted background, profiles show `sum_y(data - background)` at each
  spatial pixel. Legends give inclusive raw y ranges and any reduced row coverage.
  The curves are not recentered; a horizontal line marks zero.
- Displayed profiles use units of `10^3 e-`; the plot divides signals and limits
  by 1000 without changing the saved electron arrays or extraction.
- A QC packet can explicitly select a saved two-sided PypeIt fit through
  `profile-background.json`. Its manifest, image arrays and recipe are hash-bound;
  the raw data, wavelength map and detector window must match the current packet.
- External models are displayed only inside the common interval bracketed by
  accepted background samples. Invalid model rows are excluded consistently from
  every spatial column; missing detector samples are never treated as zero.
  All candidate positions remain inside the profile axes, even when a candidate
  falls outside that supported interval; no background curve is extrapolated there.
- Without a selected fit, profiles remain labeled as medians including sky.
  Negative profile values stay plotted; narrow downward outliers affect neither
  source counts nor extraction and are excluded only from the display-limit calculation.
- The initial SN2026ayt profile experiment used the saved C2 quadratic PypeIt
  trial without changing its parent reduction. The later reviewed-source rerun
  below recomputes the background and extraction using the user's visual C2
  identification; its 2D panels and profiles use that new fit.

A fitted two-dimensional local background can remove smooth host light as well
as sky, but it does not establish a validated host-galaxy decomposition beneath
the supernova. Source identity, a near-zero background profile and successful
extraction do not independently validate host subtraction.

## Verified 5 November 2026 — both complete observing nights

- Both final `runs/YYYY-MM-DD/index.html` pages retain the approved 29 October
  layout, with the **ePESSTO+ / EFOSpec** masthead. Calibration checks are ordered
  AT, SN, then other sources; failed or unvalidated checks are red. Selected
  calibration manifests are included even when stored outside `calibrations/`.
- **2026-10-28**, revision `20261105T003458Z-8d3f58`: all 20 selected exposures
  attempted; seven spectra (four science, three standards), seven failures and
  six unsupported exposures. SN2026ayt retains the visually confirmed C2 recipe.
  Both AT2026agzp and SN2026aebl still require background review; five exposures
  still fail sky-flexure checks. This full-night revision replaces the target-only
  delivery pointer without deleting that earlier revision.
- **2026-10-29**, revision `20261105T003942Z-333cad`: all 18 selected exposures
  attempted; ten spectra (six science, four standards), two sky-flexure failures
  and six unsupported exposures. SN2026aadx C3, SN2026afqd and AT2026aevu now
  extract successfully. The report stages complete; native checks remain partial.
- SN2026aadx uses the user's visual C3 identification and explicit raw-x bands
  `[482, 502)` and `[575, 605)`. Its quadratic PypeIt background fit converged
  with at least 14 accepted samples on each side in every supported row. The
  iteration allowance increased from 35 to 100; clipping and acceptance gates
  were unchanged.
- SN2026afqd previously failed because two weak, broad detections had FWHMs of
  34.6 and 36.3 pixels. Their approximately 52/54-pixel exclusion radii consumed
  the left background. The reviewed C3 recipe uses clean raw-x bands `[516, 531)`
  and `[570, 600)`. Its quadratic fit now has at least 12 accepted samples on each
  side, no invalid rows, and reduced chi-squared 0.654. This is a background review;
  the target association remains unverified and host deblending is not established.
- Numerical products live in each revision's `reduction/products/`; QA, masks,
  native diagnostics and provenance remain alongside them. Review these experimental
  products before quantitative analysis; extraction success is not calibration
  acceptance. Gr16 requirements are listed above; HostSub_GP remains a future task.
- Both portable reports pass offline image loading, AT/SN ordering, red-status,
  mobile-width, enlargement and byte-identical FITS-download checks. All 2,204
  protected raw/earlier-revision files remain unchanged. Per-night evidence is
  `report-verification.json`; the display-only profile refresh preserves the prior
  QC/report and records unchanged reduction files in
  `archive/profile-crop-20261105/refresh.json`.
- Verification: 282 tests pass with 86.91% coverage. A final display-only export
  margin adjustment keeps the enlarged rotated labels inside the PDF/JPG/PNG;
  its source snapshot and unchanged-reduction checks are retained under
  `archive/profile-label-margin-20261105/`. The exported profiles were inspected
  visually and their image borders checked for clipping.

## Verified 4 November 2026 — reviewed source and second night

- Night **2026-10-28**, revision `20261104T174814Z-80ab9e`: the explicitly
  selected SN2026ayt exposure was re-extracted with the reviewed C2 recipe.
  Log, reduction and report completed with one spectrum and no failed exposures.
  This is a target-only revision; the earlier full-night runs remain archived.
- Night **2026-10-29**, revision `20261104T174347Z-9b592a`: all 18 selected
  science/standard exposures were attempted. Seven spectra were produced, five
  exposures failed and six configurations remain unsupported by the archive path.
  The report completed; native calibration checks remain partial.
- The five failures comprise two sky-flexure checks, one bounded-background
  support failure and two unresolved source selections. Repeating unchanged
  reductions does not resolve those decisions or validate unsupported setups.
- Subsequent profile styling regenerates diagnostics from saved arrays only;
  it does not require another scientific reduction.

## Verified 3 November 2026 — observing night 2026-10-28

- Final revision: `runs/2026-10-28/nightly/20261103T162629Z-7d17a0/`.
  All 20 science/standard exposures were attempted: six spectra, eight explicit
  failures, six unsupported archive configurations. The report stage completed.
- The five original sky failures, two ambiguous-source failures and six archive
  setup skips remain unresolved. A PypeIt correlation result was obtained for
  every original sky failure, but it does not remove weak/disagreeing line evidence.
- The current bounded-background policy also stops AT2026agzp: the broad neighbour
  prevents clean two-sided bands. Increasing the trial window from 141 to 241
  pixels did not establish adequate support. Its new diagnostic packet retains
  candidates, acquisition images and replayable recipes without accepting a source.
- All nine selected native calibration groups were checked against this night's
  exposures. Native validation retained 12 measured optical sky offsets, six sky
  failures and two unvalidated Gr16 red-sky comparisons. No native correction was
  substituted into archive products.
- Delivered 34 wavelength-check packets with PDF/JPG figures, nine readable
  PypeIt `spec2d` files and three source/background review packets.
- Verification: 254 tests passed, 87.39% Python coverage, wheel build passed.
  PypeIt's `show_2dspec --list` and `chk_wavecalib` read the generated/selected
  files. The portable report loaded 66 figures offline, passed enlargement and
  narrow-screen checks, and its six FITS downloads matched the original bytes.
- All 1,263 recorded pre-existing files and all 72 selected native master files
  were unchanged. Source snapshots match the final code. Detailed evidence is
  `methodology-verification.json` and the dated logs in the final revision.
