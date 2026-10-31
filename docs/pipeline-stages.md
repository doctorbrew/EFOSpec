# What runs where

The current `reduce-rapid` workflow is **PypeIt extraction with an ePESSTO+
archived-calibration bridge**. It does not execute IRAF/PyRAF. It supports the
inspected EFOSC2 2×2, Free-filter Gr11/Gr13 modes; SOFI remains a later phase.

| Stage | Implementation | Current behaviour |
| --- | --- | --- |
| Inventory and reference selection | ePESSTO+, Astropy | Read FITS headers, hash inputs, associate archived arc/sensitivity references, preserve historical filenames. |
| Detector preparation | ePESSTO+, NumPy | Apply the legacy rapid trim, convert ADU to electrons using header gain, crop around the expected source. No bias, flat, dark or overscan correction. |
| Wavelength solution | ePESSTO+, NumPy/SciPy | Refit a 2D polynomial to archived IRAF arc identifications. Measure flexure from 5577/6300 Å sky lines; check 6364 Å independently when measurable. PypeIt's wavelength-calibration solver is not run. |
| Source finding and sky | PypeIt 1.14.0 | `PypeItImage` carries detector/noise information; `FindObjects` detects and traces sources and fits the global sky. ePESSTO+ supplies a straight cropped slit and selects the target using historical aperture geometry or a flagged nominal position. |
| Extraction | PypeIt 1.14.0 | `Extract` models local sky and object profiles, performs optimal and boxcar extraction, and supplies variance estimates. Other detected sources remain in the joint model. |
| Flux calibration | ePESSTO+, archived references | Apply archived logarithmic sensitivity and the La Silla extinction curve with explicit gain/exposure/dispersion factors. No new sensitivity function is fitted by PypeIt. |
| Output | PypeIt + ePESSTO+ | PypeIt `SpecObjs` writes native electron-count spec1d FITS with vacuum wavelengths. PypeIt air/vacuum conversions are used. Custom bin-overlap resampling propagates flux and diagonal variance onto the air-wavelength grid, then writes historical FITS/ASCII products. |
| Figures and webpage | ePESSTO+, Matplotlib, HTML | Plot the saved arrays; compare against IRAF products only if present. Build the offline Fieldnotes report automatically. No science is recomputed in the webpage. |

Code: `src/epessto_plus/rapid.py` orchestrates extraction;
`archive_calibration.py` implements the reference conversion and resampling;
`pypeit_adapter.py` supplies instrument parameters; `report.py` builds the page;
`scripts/preview_spectrum_style.py` renders its figures.

## What is still missing

The demonstrated night has no raw arc, bias or flat calibrations. Native PypeIt
calibration-master generation, slit-edge calibration and a fresh standard-star
sensitivity solution are not implemented in this rapid path. `plan` can inventory
and associate raw calibration candidates; it does not reduce them.

Telluric correction is absent, fringing remains, red second-order contamination
and absolute flux accuracy are not fully validated, and resampling covariance
is not exported. Five of the 13 demonstration science targets use an unverified
nominal acquisition position. Products remain `EXPERIMENTAL`/`Rapid`; neither
full legacy parity nor ESO Phase 3 certification is claimed.

The saved sky-background shading represents input to the global fit before
iterative rejection. Spatial-profile aperture shading shows the actual geometric
boxcar region, not the weights of the optimal extraction.
