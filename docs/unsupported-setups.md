# Unsupported setups: development requirements

Status on 5 November 2026: separate native Gr13/GG495 standard extractions are
implemented and seven observed exposures now have count products. Native Gr16
science delivery and independent flux validation remain unfinished.

The two complete October nightly revisions skip 12 exposures: five Gr16/OG530
and seven Gr13/GG495. Eleven are standard-star exposures; the science exposure
is AT2026twd, `EFOSC.2026-10-30T04:59:22.399.fits`. Its separate Gr11/Free
exposure already reduces. VMa2 and L745a are recorded as `STD` observations,
not halogen lamps.

## What already exists

- All 12 skipped exposures have selected raw arcs, biases and flats. The
  AT2026twd Gr16 exposure has one arc, ten biases, three flats and a same-setup
  VMa2 standard candidate. Candidate selection does not establish acceptance.
- Native diagnostic masters exist for both setup families. The selected
  29 October Gr16/slit1.5 group `4dede8a4db95d85c` identifies 15 arc lines,
  with 0.0861-pixel fit RMS and 0.1234-pixel held-out RMS. Its accepted line
  bracket is 6679.995–9787.186 vacuum Angstroms; the wider detector wavelength
  map must not be confused with validated extrapolation.
- The paired native runner already enables Gr13/GG495 at the configuration
  gate. This does not mean it has passed real-data extraction or flux validation.
- The default nightly archive bridge enables only Gr11/Gr13 + Free at 2x2.
  PypeIt extraction is downstream of that gate. Installing PypeIt does not
  supply our missing setup-specific validation or nightly integration.

`native-readiness` and each new `setup-checks.json` now expose a
`pipeline_support` record per exposure. It separates archive eligibility,
experimental native master/paired-run coverage, development requirements and
scientific validation. Skipped records retain that record and a specific reason
and action. Existing products and nightly reports are not rewritten by this
diagnostic change.

## Delivered: separate filtered standards

`efospec reduce-filtered` processes one explicitly named night. It uses raw
bias/flat/arc calibration and the shared PypeIt extraction, with the strongest
positive central source and bounded two-sided background. It produces native
spec1d/spec2d, count-table FITS, ASCII counts with statistical errors and validity
masks, extraction provenance, and an offline HTML supplement using the existing
nightly renderer and QC figures.

```sh
efospec reduce-filtered data/2026-10-28 --night 2026-10-28 \
  --output runs/2026-10-28/filtered/NEW_REVISION
```

The separate 29 October invocation can replay the retained, exposure-bound
background review:

```sh
efospec reduce-filtered data/2026-10-29 --night 2026-10-29 \
  --output runs/2026-10-29/filtered/NEW_REVISION \
  --background-reviews runs/2026-10-29/validation/filtered-background-20261105/reviews.json \
  --calibration-group runs/2026-10-29/filtered/20261105-native-v1/exposures/EFOSC.2026-10-30T03:09:45.142/calibration \
  --calibration-group runs/2026-10-29/filtered/20261105-native-v1/exposures/EFOSC.2026-10-30T03:15:22.641/calibration
```

That review also binds the exact calibration manifest, hence the explicit
paired-native calibration directories above. Diagnostic-only groups use a different
contract and are rejected by this option. Changed raw files, recipes, crops,
pixels, wavelengths or calibration identity invalidate a background review.

Verified local outcomes:

- **28 October:** four count spectra, two experimental L745a response curves;
  `runs/2026-10-28/filtered/20261105-native-v2/index.html`.
- **29 October:** three count spectra, one experimental L745a response curve;
  `runs/2026-10-29/filtered/20261105-native-v3/index.html`.
- Products live in each revision's `exposures/EXPOSURE/products/`, native
  PypeIt products in `native/`, and fitted responses beside `extraction.json`.
  Counts use electrons per spectral pixel and vacuum, topocentric Angstroms;
  `FLUXCAL=NONE`. Response fits are separate, explicitly unvalidated artifacts.
- All four VMa2 extractions retain counts despite the unavailable physical
  reference. L745a response recovery is training-standard closure only.
- Extraction is restricted to the common two-dimensional arc-reference
  bracket before fitting the sky. This resolved the 28 October VMa2
  convergence failures without changing degree, clipping or convergence gates.
- One 29 October VMa2/slit1.0 exposure required reviewed background geometry.
  A broad candidate near raw x=583 prevented automatic placement; a wider
  window did not resolve it. The retained recipe uses [500,530) and [600,630),
  degree 2, sigma clipping 4 and a measured central-profile FWHM of 7.079 pixels.
  Its accepted fit retains at least 26 samples per side. The review was made
  during pipeline development; it does not claim observer-confirmed identity.
- Original nightly reports, earlier attempts, raw frames and calibration
  masters remain unchanged. These supplements do not replace the current
  archive-reduction products or clear their unsupported-setup labels.

Each completed revision retains `verification.json` and its replay script,
covering raw/master/product hashes, FITS checksums, units and masks, reference
brackets, two-sided background support, offline downloads, 390-pixel layout,
figure enlargement, and PDF plus 300-dpi JPG exports.

Final regression run: **293 tests passed, 87.35% coverage**. The tests include
synthetic raw photons through native calibration, filtered extraction, count
export, experimental response and portable report, plus rejection of changed
background-review inputs. Each completed revision retains `regression-tests.log`
and the tested source hashes in `regression-verification.json`.

## Development order

1. **Filtered standards:** reduce Gr13/GG495 through the raw-only path with
   native variance, bounded background and supported wavelength masks. Validate
   L745a against its registered physical reference; register and verify VMa2
   independently. Retain counts separately from response-calibrated products.
2. **Gr16 counts and wavelength:** connect the existing native master builder
   to the extraction/export path. Verify geometry and calibration hashes.
   Establish a red-sky correction using physically supported features, with
   held-out features or wavelength windows. Test shifts of both signs, missing
   features and disagreement. The current 5577-A requirement cannot apply;
   the saved red correlation alone cannot authorize a correction.
3. **Response:** derive setup-specific sensitivity from the observed standards,
   check wavelength-block holdouts and independent observations, and measure
   supported coverage, fringing and telluric limitations. Preserve masks and
   distinguish statistical errors from calibration uncertainty. Do not reuse
   a Free-filter response for a filtered exposure.
4. **Nightly integration:** publish accepted native products in a new dated
   revision with their calibration method and provenance. Preserve previous
   products, unsupported/failure evidence, target-identity flags and the approved
   report template. Validate AT2026twd first, then each named night separately.

Gr13/GG495 standard observations were used by the legacy pipeline to correct
Gr13/Free second-order contamination (`efoscspec1Ddef.py`). Extracting a filtered
standard does not itself apply that correction. On 5 November the observer
selected separate filtered reductions first; second-order correction is deferred.
ESO documents historical filter-label ambiguity; usable throughput should be
measured from these observations instead of assuming a precise cutoff from the
name alone. See [ESO order-sorting documentation](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/inst/order-sorting.html).

## Observer decisions (5 November 2026)

- Develop separate filtered reductions first. Preserve the Free/GG495 pairing
  information, but do not apply a second-order correction in this phase.
- No additional wide-slit standards, trusted reduced spectra or calibrated
  photometry are available. Begin with the retained raw data; keep absolute
  flux and independent uncertainty validation explicitly unestablished.

These decisions do not waive acceptance checks. The VMa2 header position fails
the installed PypeIt physical-reference catalogue match within 100 arcsec, and
our native fallback currently registers only L745-46A. Resolve the reference
through a documented physical catalogue and coordinate/epoch check; do not
force a match using the abbreviated OBJECT name.

Host-galaxy subtraction remains outside this development scope.
