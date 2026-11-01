# Implementation tasks

Parent: [migration design](README.md). Tasks are local; no tracker issues have
been published. Status describes actual work, not promised scientific support.

## Next interface phase

- First priority: [native calibration without IRAF-derived inputs](../../native-calibration.md).
- [D1–D5: desktop extraction app, worker integration, and nightly log](gui.md).
- Qt desktop and shared extraction/recipe workers are implemented; see the desktop validation record.
- Desktop platform validation and extended-source accuracy remain explicit acceptance gates.

## Completed rapid demonstration (2024-11-14 data)

An experimental bridge now spans parts of T3–T5: archived air-wavelength IDs,
independent sky shifts, native PypeIt finding/sky/optimal and boxcar extraction,
legacy response/extinction conversion, flux-conserving export and native FITS
round trips. All 13 science exposures produced outputs; eight have historical
aperture anchors, five retain unverified target-association flags. Two L745a
standard exposures provide independent flux comparisons. Current automated results
are published by the [build workflow](https://github.com/sPaMFouR/EFOSpec/actions/workflows/build.yml).

See [measured evidence](evidence.md#2024-11-14-rapid-reduction-demonstration).
This bypasses the missing raw-calibration requirement only for the explicit
rapid archive experiment. The full-native acceptance criteria below remain
open. Priority work is now raw-calibration acquisition, target association,
native calibration generation, red fringing/second order, and consumer parity.

## T0 — Inventory and pure science naming

Status: complete (bounded foundation). Depends on: none.

Delivered: source/package separation from `ntt`, read-only inventory, SHA-256
and duplicate/identity reporting, standard-candidate and processed-frame
separation, explicit rapid/full science names, noon-UTC night boundary and
explicit processing MJD. 17 unit/integration tests pass; the supplied template
name is reproduced. Real-data inventory is saved locally under ignored outputs.

Limitations: no setup generation, calibration selection, persistent product
registry, calibration-product names, pixel reduction or exporter. Other raw
geometries and extension-based FITS data require later support.

## T1 — Freeze a complete Gr13 baseline and reference library

Status: Gr13/slit1.0 raw candidates retrieved; scientific baseline validation pending. Depends on: T0.

- [Retrieved inputs and hashes](../../native-calibration.md#raw-gr13-inputs-now-retrieved): one arc, seven flats, ten biases.
- Candidate checks pass for SN2023xxj and existing Gr13/slit1.0 standards.
- ESO marks the association uncertified; biases are from 7 November.
- Native wavelength/sensitivity execution is demonstrated separately on one Gr13/Free pair; full baseline and other configurations remain unvalidated.

Outcome: one reproducible, complete Gr13/Free/slit1.0 night with both input
calibrations and legacy reference products.

- [ ] Locate raw arcs, at least three biases and flats per applicable group,
  and spectrophotometric standards with complete setup/OB/time metadata.
- [ ] Locate GG495 comparison standards if red Gr13 flux claims are required.
- [ ] Record raw/reference SHA-256, archive identifiers, licences/access locations,
  standard-library version and extinction-file hashes.
- [ ] Freeze legacy software/options, extraction choices, logs, databases and
  baseline products, identifying rapid versus full.
- [ ] Confirm multispec bands, wavelength medium and topocentric reference from
  fixtures plus physical line identifications.

Verification: another operator can reconstruct the same input manifest and
legacy baseline. A reduced archived arc is not accepted as raw calibration.
Public repository contains manifests/retrieval instructions and permitted small
fixtures, not the user's raw science directory.

## T2 — Plan calibration associations before execution

Status: partially implemented; complete-night acceptance depends on T1.
Depends on: T0.

Delivered: raw arc/bias/flat grouping, explicit raw arc precedence, physical
compatibility checks, 100-arcsec legacy catalogue matching, same-setup standard
associations, reference hashes, deterministic plans and missing/ambiguous states.
Rapid disables bias/flat and requires explicit raw arcs until archive conversion
exists. Archive masters, remaining explicit override types and name reservations
are still pending. This does not claim complete historical selection parity.

Outcome: deterministic plan with explainable choices and explicit overrides.

- [ ] Implement calibration-type-specific matching and historical precedence,
  including wide-slit arcs, same-OB flats, catalogue-matched standards and
  grism/filter sensitivity rules.
- [ ] Record raw/master distinction, setup validity, age, source and selection
  reason; reject conflicting archive identities and missing required metadata.
- [ ] Test ties, missing inputs, incompatible filters/binning/readout, mixed
  nights, missing slit metadata, override precedence and archive fallback.
- [ ] Persist processing date and a collision registry; implement remaining
  calibration filename contracts and atomic reservations.
- [ ] Separate historical matches from physical-compatibility warnings. No
  arbitrary age limits or silent changes to calibration policy.

Verification: synthetic association tests plus T1's hand-reviewed night; a
serialized plan is stable under input-path ordering and reruns. No reduction.

## T3 — EFOSC2 driver and Gr13 wavelength experiment

Status: experimental raw processing, physical arc fitting and one Gr13/Free pair
demonstrated. Broader scientific acceptance still depends on T1/T2.
See [native evidence](../../native-desktop-validation.md).

Outcome: native PypeIt spec1d/spec2d from one validated Gr13 configuration.

- [x] Use the user's existing Conda `pypeit` environment (PypeIt 1.14.0) for native
  integration tests; record actual imported dependency versions. No upgrade.
- [x] Pass a custom spectrograph instance to the public `PypeItMetaData` interface;
  no monkey-patching or site-packages changes. Reduction-runner loading is pending.
- [x] Test frame typing using ESO DPR TYPE/TECH/CATG, preserving original OBJECT;
  include filter and relevant detector mode in configuration grouping.
- [ ] Lock the full future reduction dependencies and downloaded reference data.
- [ ] Verify orientation, sections, gain/read noise and BPM on 2012 and 2024
  examples; test native raw handling before any legacy trimming is applied.
- [ ] Build a Gr13 template from verified raw lamps, with traced line origins
  and vacuum wavelengths; inspect slit edges, tilts and residuals.
- [ ] Test independent arc/sky lines and explicit flexure/reference-frame
  settings. Verify actual effective parameters, not just config text.
- [ ] Select target extraction explicitly; test host/field-star ambiguity.
- [ ] Record failure modes and do not claim broader EFOSC2 support.

Verification: retain configuration, intermediate calibrations, line-identification
QA, extracted products, software lock and measured residuals. The experimental
`reduce-native` pair command exports products; the default nightly path remains unchanged.

## T4 — Flux, second order, telluric and errors

Status: observed-standard response and uncertainty propagation implemented;
absolute-flux, telluric and second-order validation remain open. Depends on T1/T3.

Outcome: calibrated spectra with traceable reference standards and uncertainty.

- [x] Match standards to independently sourced physical flux references and
  extinction curves; derive native sensitivity without IRAF response arrays.
  Compare reference conventions with legacy after independent processing.
- [ ] Verify standard/science airmass correction, response coverage, slit-loss
  policy and lack of unintended extrapolation.
- [ ] Validate Gr13 Free/GG495 second-order treatment on independent standards;
  quantify any interim wavelength restriction.
- [ ] Implement explicit optional telluric treatment with masks and uncertainty.
- [ ] Test FLAM scaling, positive inverse variance, invalid samples, cosmic rays,
  and sky residuals; independent/repeated standards assess flux accuracy.

Verification: measured wavelength-dependent flux ratios, uncertainty diagnostics
and sensitivity source details; document improvements/differences from legacy.
Coaddition is deferred until per-exposure calibration and object identity pass.

## T5 — Compatibility export and observer workflow

Status: blocked on T4 and confirmed product conventions from T1.
Depends on: T2, T4.

Outcome: a PypeIt-backed workflow delivering legacy names and supported formats.

- [ ] Implement explicit wavelength medium/frame conversion and flux-conserving
  resampling with mask/variance handling and recorded correlation limitations.
- [ ] Export verified multispec bands, WCS, physical 1D units, association headers
  and unchanged two-column ASCII semantics; resolve 2D BUNIT discrepancy with
  fixtures and documented consumer expectations.
- [ ] Validate legacy consumer reads, naming/idempotence, product references,
  source details and new backend/version headers. Never assign unsupported Final QA.
- [ ] Compare rapid to rapid and full to full using both baseline and independent
  scientific evidence; document explicit accepted numerical differences.
- [ ] Add optional backend dispatch to existing commands only after parity gates;
  include checked execution, restart behaviour and a visible review state.

Verification: end-to-end fixture tests plus operator review on T1's night.
ESO archive delivery, if required, must pass its actual current validation
requirements before any Phase 3 compliance claim.

## T6 — Broader EFOSC2 rollout

Status: blocked on T5. Depends on: T5.

Outcome: validated configuration matrix and an agreed operational rollout.

- [ ] Extend Gr11 and Gr16/OG530 with independent nights; later Gr18/20, GG495,
  wide slits and other binning/readout as data permit.
- [ ] Add explicit object-selected coaddition and traceable product naming;
  test variable targets and prevent unintended cross-epoch combinations.
- [ ] Provide operator QA for traces, sky windows, calibration substitutions and
  telluric/flux decisions; save choices in the manifest.
- [ ] Submit generic instrument fixes/templates upstream when ready; preserve
  the pinned dependency until their replacement is verified.
- [ ] Agree release thresholds and collaborator acceptance before making PypeIt
  default. Keep legacy rollback through the transition.

## Decisions still requiring evidence

- **D1:** legacy wavelength medium and exact band semantics — resolve in T1.
- **D2:** calibration age limits and acceptable archival substitutions — use
  existing operational policy and T2's exposed selections; no invented limits.
- **D3:** driver extension versus a short-lived pinned PypeIt fork — resolve
  through T3. Metadata inspection now uses an instance-based subclass on 1.14.0;
  end-to-end reduction integration still needs validation.
- **D4:** quantitative scientific gates and delivery consumers — refine with
  measured T3/T4 evidence and collaborator review, including Phase 3 needs.
- **D5:** desired preservation/fix of historical 2D scaling and telluric sigma —
  maintain names and explicit semantics, document intentional corrections in T5.
