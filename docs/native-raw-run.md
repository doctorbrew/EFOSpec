# Experimental raw-only reduction

- Gr11/Gr13, Free/GG495, 2×2; centered slit1.0/slit1.5.
- Real end-to-end demonstration: one Gr13/Free exposure; broader setup validation remains pending.
- Requires raw science, ≥3 biases, ≥3 flats, an arc, and a compatible raw standard.
- Uses existing association/naming policies; no IRAF/PyRAF execution or archived calibration fallback.

```sh
efospec reduce-native data/YYYY-MM-DD \
  --science data/YYYY-MM-DD/SCIENCE.fits \
  --standard data/YYYY-MM-DD/STANDARD.fits \
  --science-position 548 --standard-position 548 \
  --output runs/YYYY-MM-DD-native
```

- Positions are raw, binned, zero-based spatial pixels; verify them from acquisition/trace evidence.
- Default 548 is an acquisition hypothesis; output records the unverified association.
- Outputs retain legacy primary filenames, four flux bands, validity masks and air wavelengths.
- `FLUXCAL=NATIVE` distinguishes the freshly fitted response.
- `--skip-report`: omit plotting. `--reuse-calibrations PRIOR_RUN`: reuse only matching, hash-verified raw-derived groups.
- Every attempt needs a fresh output directory; failures retain their log/manifest.

## Processing

1. PypeIt builds bias, slit edges, arc, tilts and flat masters.
2. EFOSpec matches raw He–Ar peaks to physical wavelengths; PypeIt fits the solution.
3. Physical range, dispersion, retained-line span and whole-line holdouts gate acceptance.
4. PypeIt propagates detector variance, flat scaling and bad/cosmic-ray masks.
5. Isolated 5577/6300 Å fits measure flexure; 6363 Å independently checks it.
6. PypeIt extracts the standard and fits a new sensitivity function.
7. Shared PypeIt extraction and EFOSpec export produce science spectra and Fieldnotes.

## Physical references

- Arc wavelengths: [ESO EFOSC2 manual, Table 17](https://www.eso.org/sci/facilities/lasilla/instruments/efosc/doc/manual/EFOSC2manual_v4.2.pdf); no archived pixel IDs.
- Standards: PypeIt's physical catalogues, matched within 100 arcsec.
- L745-46A: checksum-pinned [Bessell January 2009 table distributed by PyWiFeS](https://github.com/PyWiFeS/pywifes/blob/e854c3648d81ff940c84036082e114c5a6e57b62/reference_data/l745-46a_v2.tab).
- L745 air-wavelength convention follows PyWiFeS' native AIR convention; the historical ASCII header does not explicitly identify the medium.
- The L745 table is downloaded into the private run and hashed; no PyWiFeS installation is required.
- VMa2 lacks a registered reference here and stops before calibration work.
- Extinction: PypeIt's La Silla table; source paths/checksums are recorded.

## Scientific limits

- Successful execution is not a claim of absolute spectrophotometric accuracy.
- Narrow-slit losses, transparency changes, tellurics and Gr13 red second-order contamination remain.
- Statistical errors omit response-fit and calibration systematics.
- Standard exposures may lack measurable sky lines; their arc-only wavelength status is explicit.
- Products remain experimental, without ESO Phase 3 certification.
- This branch's raw builder overlaps work in the separate debugging thread; reconcile implementations before merging.
