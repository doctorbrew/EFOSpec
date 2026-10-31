# Legacy EFOSC2 spectroscopy compatibility contract

Evidence is from upstream commit `2b4b28dca7b2360b1b6259bd46920aaa47054e63`.
The local working baseline at `75eb12d9e1323bc7b34a6070f2fb7523b793f50d` has
the same tracked spectroscopy source. This is an implementation audit, not a
claim that every historical branch is scientifically correct.

Paths below are relative to `trunk/`. Source line numbers identify inspected
context and may change; function names and behaviours define the contract.

## Metadata and naming

`src/ntt/util.py:117–240` (`readkey3`) removes `#` from string metadata.
Observing night is `DATE-OBS - 12 hours`, formatted YYYYMMDD. Preserve UTC and
fractional-second exposure identity. Its `JD` accessor is actually `MJD-OBS +
0.5`; preserve any relevant selection behaviour without adopting this misleading
name in the new model.

Science OBJECT normalization removes spaces and substitutes `_` for `/`.

| Product | Legacy name |
| --- | --- |
| Rapid rectified 2D | `t{object}_{night}_{grism}_{filter}_{slit}_{n}.fits` |
| Full rectified 2D | `t{object}_{night}_{grism}_{filter}_{slit}_{processing_MJD}_{n}.fits` |
| Extracted / fluxed / fluxed 2D / telluric corrected | Base plus `_ex` / `_f` / `_2df` / `_e` before `.fits` |
| Rapid ASCII | Fluxed basename with `.asci` |

Anchors: `efoscfastspecdef.py:59–90`, `efoscspec2Ddef.py:251,645–655,832`,
`efoscspec1Ddef.py:561–620`. Full preprocessed science has the same base without
the leading `t`. The processing MJD comes from the local processing calendar
date; freeze it in the run manifest rather than recomputing it on resume.

`util.name_duplicate` (`:920–944`) reuses a matching DATE-OBS product or picks
the lowest free positive integer, starting at 1. Its glob only sees suffixes
up to two characters. The new naming helper deliberately handles >99 and
rejects ambiguous duplicate identities. It does not yet implement a persistent
reservation registry or the full calibration-product naming scheme.

Calibration names include `bias_{night}.fits`,
`bias_{night}_{grism}_{filter}_{processing_MJD}.fits`,
`flat_{night}_{grism}_{filter}_{slit}_{OBID}_{processing_MJD}.fits`,
`nflat_…`, `arc_{science_name}`, and
`sens_{night}_{grism}_{filter}_{standard}_{processing_MJD}_{n}.fits`.
See `efoscspec2Ddef.py:380,490,562,595,739` and `efoscspec1Ddef.py:252–260`.

## Calibration selection and profiles

| Behaviour | Rapid | Full |
| --- | --- | --- |
| Detector corrections | Trim; no bias/flat/overscan/dark | Bias/flat enabled by default; CLI flags can disable |
| Cosmic rejection | Optional | Optional |
| Arc source precedence | Explicit list, archive | Explicit list, input-night arcs, archive |
| Arc match | Grism/filter/slit, nearest absolute MJD | Same |
| Wide-slit arc exception | `slit5.0` uses `slit1.0` | Same |
| Sensitivity match helper | Grism/filter, nearest MJD; slit ignored | Same helper; same-setup standards tried first |
| 1D extinction | `extinction_lasilla.dat` | `lasilla2.txt` |
| Shared 2D extinction | `lasilla2.txt` | `lasilla2.txt` |
| Sensitivity spline order | 6 when generated | 16 |
| Legacy quality label | Rapid | Final |

These policies are explicit profile inputs, not interchangeable defaults.
Archive fallback remains an explicit, traceable mode. Historical helpers lack
maximum-age and detector-compatibility checks; new checks must report conflicts
with legacy choices rather than silently presenting a changed choice as parity.
Anchors: `util.py:454–535`, `efoscfastspecdef.py:37–40,89–101,213–214`,
`efoscspec2Ddef.py:730–736`, `efoscspec1Ddef.py:272–292,419–436`.

Full standards are identified within 100 arcsec of the bundled
`standard/stdlist/standard_efosc_mab.txt`, not solely by OBJECT. The new inventory
only identifies header-based candidates; catalogue verification is pending.
Biases require at least three frames per night for median/ccdclip combination,
then nearest local/archive fallback. Flats prefer `OBJECT=flat` over `dome`,
group by setup and OBID, require at least three, combine with mean/no rejection,
then normalize via `apflatten`. Prefer the science OBID, else nearest time.
Explicit supplied flats bypass master construction. Blue rows are forced to
unity in normalized flats: Gr13 1:200, Gr11 1:300, Gr18/20 1:50. These choices
must be tested before replacement by generic PypeIt flats.
See `efoscspec2Ddef.py:173–194,369–404,430–458,545–707`.

## Geometry, arcs and flexure

Legacy discovery expects 1030×1030 images and commonly `fastL` readout. FITS
sections are 1-based and inclusive. Dispersion is along axis 2. These sections
are not valid for arbitrary binning/window modes without conversion:

| Setup | Trim section |
| --- | --- |
| Gr13 Free | `[100:950,1:1015]` |
| Gr13 GG495 rapid | `[100:950,208:1015]` |
| Gr13 GG495 full | `[100:950,250:1015]` |
| Gr13 OG530 | `[100:950,300:1015]` |
| Gr16 | `[100:950,1:950]` |
| Full Gr11/18/20 with GG495 | `[100:710,40:1015]` |
| Other defaults | `[100:950,5:1015]` |

Anchors: `efoscfastspecdef.py:65–78`, `efoscspec2Ddef.py:412–430`.

Line references are `standard/ident/Lines_HgCdHeNeAr600.dat` and archived IRAF
arc identification databases. Full initial identification uses Legendre order
5; rapid uses order 3. Both trace, fit coordinates (spectral order 4), then
transform with flux conservation. See `efoscspec2Ddef.py:773–840` and
`efoscfastspecdef.py:118–142`.

Legacy line values appear consistent with air wavelengths, but no unambiguous
medium declaration was found. Verify reference sources and physical line
centroids before approving an air/vacuum export conversion. Full writes
`SPECSYS=TOPOCENT`; no barycentric/heliocentric correction was found in these
paths (`efoscspec2Ddef.py:1025`).

Sky flexure uses continuum-subtracted sky correlation, tests ±50 Å in 0.1 Å
steps, but applies an integer Å shift. Full tries this for exposure >300 s
when a sky reference exists; rapid attempts it unconditionally. A full 1D
telluric fallback is used if a shift header is absent. Preserve the intended
zero-point correction and source details, not an unjustified integer quantization.
See `efoscspec2Ddef.py:93–170,859–881`, `efoscfastspecdef.py:143–149`, and
`efoscspec1Ddef.py:151–204,400–403`. Legacy correlation xmin/xmax affect plotting,
not the correlation fitting window; tests must constrain the actual domain.

## Flux, telluric and delivery

Standards use `standard/MAB/m{standard}`. Full Gr13/Free can combine Free and
GG495 sensitivity data, scaling at 5500 Å and writing `_2ord.fits`
(`efoscspec1Ddef.py:516–536,666–715`). This requires a dedicated second-order
validation experiment; the IRAF representation must not be used as PypeIt
sensitivity data.

1D flux is exposure-normalized F_lambda in `erg/cm2/s/Angstrom`, not F_nu.
The shared 2D flux routine multiplies numerical values by 1e20 yet writes a
misleading `10^20 erg/cm2/s/Angstrom` BUNIT. Establish stored-value meaning
against fixtures and consumers before choosing an explicitly versioned fix.
See `efoscspec1Ddef.py:103–147,563–574`.

Telluric correction uses smoothed, depth-adjusted ATLAS O2/H2O spectra. The
legacy `_e` file copies bands 2–4 from uncorrected `_f`, including uncertainty.
This is a documented numerical defect, not a requirement to reproduce it.
Propagate uncertainty through the correction and identify the changed semantics.
See `efoscspec1Ddef.py:1–100,583–599`.

Observed calibrated legacy products have primary arrays `(4,1,N)`; the usual
bands are optimal flux, unweighted flux, sky and sigma. Confirm all band labels
from IRAF fixtures before writing an exporter. `util.py:1039–1059` computes S/N
using bands 1 and 4. PypeIt sky/error arrays need calibrated units and extraction
semantics; missing bands cannot simply be fabricated. ASCII output is two
header-free columns from band 1, not a three-column error table.

| Product | FILETYPE |
| --- | --- |
| Preprocessed 2D | 22104 |
| Rectified 2D | 22106 |
| Extracted 1D | 22107 |
| Fluxed 1D / 2D | 22208 / 22209 |
| Telluric corrected | 22210 |
| Sensitivity / telluric model | 21212 / 21211 |

Preserve meaningful ARCFILE, PROVn, TRACEn, ARC, ZEROCOR, FLATCOR, SENSFUN,
ATMOFILE and ASSON1/ASSOC1 associations. WCS is in Å, while Phase 3 wavelength
bounds, RMS and selected spectral summaries are in nm
(`efoscspec2Ddef.py:885–925`). Write actual backend/version and QA; never copy
unsupported fixed accuracy values (`FLUXERR=15.2`, `SPEC_SYE=0.1`) or claim
Final/ABSOLUTE purely because the old writer did.
