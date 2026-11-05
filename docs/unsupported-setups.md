# Unsupported setups: development requirements

Status on 5 November 2026: diagnostics implemented; native science delivery for
the affected exposures remains unvalidated. No reduction gate was relaxed.

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
standard does not itself apply that correction. Whether to implement correction
now or after separate filtered reductions is an outstanding scope decision.
ESO documents historical filter-label ambiguity; usable throughput should be
measured from these observations instead of assuming a precise cutoff from the
name alone. See [ESO order-sorting documentation](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/inst/order-sorting.html).

## Information requested from the observer

- Whether to include second-order correction now or first validate separate
  filtered reductions.
- Paths to any wide-slit standards, trusted independently reduced spectra, or
  calibrated photometry usable for flux validation, plus observing-condition
  notes if available. No additional data is required to begin raw processing;
  absence of external evidence limits the flux-accuracy claims we can make.

These questions do not waive acceptance checks. The VMa2 header position fails
the installed PypeIt physical-reference catalogue match within 100 arcsec, and
our native fallback currently registers only L745-46A. Resolve the reference
through a documented physical catalogue and coordinate/epoch check; do not
force a match using the abbreviated OBJECT name.

Host-galaxy subtraction remains outside this development scope.
