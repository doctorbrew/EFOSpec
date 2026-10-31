# Native calibration: inputs and status

- **Required destination:** no IRAF/PyRAF execution or IRAF-derived calibrations.
- **Current runner:** `reduce-rapid` still uses archived IRAF line IDs and sensitivity.
- **Native reduction:** not implemented or validated end to end yet.
- **First scope:** EFOSC2 Gr13/Gr11; SOFI later.

## What the local folders contain

Paths below are relative to the parent `pessto/` workspace.

| Location | Contents | Native calibration input? |
| --- | --- | --- |
| `database/ap*`, `2024-11-14/database/ap*` | IRAF aperture, trace, background settings | Comparison only |
| `database/idarc*`, `2024-11-14/database/idarc*` | IRAF identified lines and wavelength fits | Comparison only |
| `database/fcarc*`, `2024-11-14/database/fcarc*` | IRAF coordinate transformations | Comparison only |
| `2024-11-14/arc_20120825_Gr13_Free_slit1.0_56442_1.fits` | Processed arc; observed 2012-08-26; `FILETYPE=22104` | No |
| `epessto+/trunk/src/ntt/archive/efosc/` | Older processed arcs, master biases/flats and responses | Comparison only |
| `2024-11-14/EFOSC*.fits` | Raw science, standards, and imaging | Science/standards: yes |

- **Raw standards exist:** four Feige110 and four L745a exposures.
- **Setups:** Gr11/Free, Gr13/Free, Gr16/OG530; slit widths vary.
- **Missing:** raw arc, bias, and flat exposures in the inspected night.
- **Also checked:** `Anna_20241114.zip`, `Avinash_2024-11-14.zip`, and the installation-test `.tgz`.
- The archives contain no additional raw arcs, biases, or flats.
- `DATE-OBS` falls on 15 November UTC for this 14 November observing night.
- A `DPR TYPE=WAVE` header alone does not make an arc raw; inspect processing markers too.

## Check another directory

```sh
python -m epessto_plus native-readiness /path/to/night /path/to/raw-calibrations
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

- Obtain the original raw calibration exposures with their ESO identifiers.
- Match binning/readout and grism/filter/slit; retain acquisition metadata.
- Build bias/flat masters from raw frames through PypeIt.
- Fit wavelength/tilts from raw lamps and independent physical line lists.
- Validate Gr11/Gr13 solutions with held-out arc and night-sky lines.
- Match observed standards to independently sourced physical flux references.
- Derive sensitivity from those observations; validate extinction and slit losses.
- Preserve legacy delivery names, wavelength conventions, units, and uncertainty bands.
- Test raw-to-delivery execution with the entire legacy calibration directory unavailable.
- Compare the resulting products with IRAF only after native processing succeeds.

Full implementation remains tracked in [T1–T5](roadmap/pypeit-migration/tasks.md).
