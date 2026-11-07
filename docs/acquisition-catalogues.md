# Acquisition catalogue QC

`efospec acquisition-catalogues` adds catalogue positions to acquisition images,
independently of spectral extraction. It does not choose a transient trace,
identify a host, or subtract a galaxy.

```sh
efospec acquisition-catalogues 2026-10-29 \
  --target SN2026aadx \
  --output runs/2026-10-29/QC/catalogues-NEW_REVISION
python scripts/build_epoch_fieldnotes.py 2026-10-29
```

Omit `--target` to process all AT/SN acquisition fields in that night's current
observing log. Repeat `--target` for a selection. The next observing date is a
separate invocation. Outputs must use a fresh directory within that date's QC
folder. Raw acquisitions are associated through their observing-block ID, not
their generic `OTHER` object name. The selected science and acquisition hashes
are retained and checked; spectral extraction and accepted products are unchanged.

## Astrometry

- Requires local Astrometry.net `solve-field` and installed reference indexes.
  `--solver` selects the executable. No images are uploaded to a solving service.
- Current support: two-dimensional, 2x2-binned EFOSC2 acquisitions. Pointing is
  only a search hint (0.3-degree radius); it is never substituted for a WCS.
- Solve each acquisition separately and retain the solver log, WCS and star
  correspondences. Raw FITS headers remain unchanged.
- Acceptance requires at least eight matches with weight above 0.9, RMS residual
  at most 2 pixels, maximum residual at most 5 pixels, scale between 0.20 and
  0.30 arcsec/pixel, and a finite WCS round-trip within 0.01 pixel.
- Residuals are internal solver consistency, **not held-out astrometric
  validation**. No acquisition-to-spectral-detector registration is performed.
- An unsolved or rejected frame gets an explicit failed status and no overlay.

## Catalogues and matching

- **NED:** the current ConeSearchByPosition API; explicitly specified degree
  longitude, equatorial J2000 coordinates transformed from FK5 to ICRS. Mark
  physical type `G` as a galaxy candidate and retain redshifts and their flags.
- **SDSS DR17:** primary PhotoObj sources; type 3 is a photometric galaxy
  candidate. The catalogue classification does not establish a host association.
- **AllWISE:** IRSA's `allwise_p3as_psd` catalogue. Retain infrared positions, W1/W2 measurements, extension and contamination
  flags as counterpart information; do not draw separate infrared markers. An AllWISE source
  or an extension flag alone is not a galaxy classification.
- Search the solved image's enclosing cone, then retain projected positions
  inside the detector. Preserve image orientation and FITS/pixel conventions.
- Record **all** other-catalogue neighbours within 2 arcsec. These are provisional
  positional associations; ambiguous matches are not forced into one identity.
  Extended galaxies can have different catalogue centroids outside that radius.
- Each request, retrieval time, raw response and SHA-256 digest is saved. Existing
  identical cached queries replay offline, including failures. A new revision
  retries the services. Queries have bounded timeouts and a 2,000-row cap; reaching
  the cap is explicitly marked truncated. Service errors are `unavailable`, not
  `no_matches`; neither an empty search nor a failed service establishes that the
  image contains no galaxies.
- `--catalogue NED --catalogue AllWISE` selects services; default is all three.
  `--timeout` sets the per-service read timeout (default 20 seconds).

## Reports and saved data

`QC/catalogue-current.json` selects records for the nightly Source QC section.
Refreshing selected targets preserves the other targets' pointers and all earlier
revisions. Report building makes no network requests. It verifies input, record,
WCS and figure hashes, then embeds the full-field/zoom overlays, galaxy table,
query statuses, positional neighbours and PDF/JPG downloads. The existing
house plot style is used, including 300-dpi JPGs.

Each revision contains `catalogues.json`; each acquisition contains `field.json`,
`astrometry/`, `catalogues/`, and its PDF/JPG/PNG overlays. The full response keeps
unclassified sources even though only galaxy candidates are plotted. Images use
plain `Galaxy 1`, `Galaxy 2`, … tags, numbered identically across both panels and
the report table. One shared legend below the panels, titled **NED galaxy candidates**
for these NED-only results, shows
`z=... (spec)` or `z=... (phot)` from the NED technique flag; missing redshifts
or methods are stated explicitly. Positional neighbours do not supply a redshift
to another source. The nightly table uses the same redshift labels. Acquisition
images use `gray_r` (higher signals drawn darker), preserving the original
pixel values and intensity stretch. Markers, legend symbols and
plain tags share the brighter coral-red `#ff8080`. Tags have no boxes or halos and
are placed fully to the left or right of their markers. Placement reserves space
around every label and catalogue marker, keeps text inside the image, and shifts
crowded labels vertically. No connecting lines are drawn. It refuses an
overlapping placement when no clear position is available. All ticks use the mandatory 30% enlargement (18 → 23.4 pt).
If another catalogue supplies galaxies, the shared legend names those catalogues too.
The galaxy-only presentation revisions are retained under
`runs/DATE/QC/host-galaxies-20261107-v9/`; earlier overlays remain on disk.

## First observed-data run, 6 November 2026

- **28 October:** 17 acquisition images checked; 10 passed astrometric acceptance
  and have overlays. Seven failed to solve or exceeded the residual gates.
  Results: `runs/2026-10-28/QC/catalogues-20261106-transients/`.
- **29 October:** 14 checked; 11 have overlays and three failed astrometric
  acceptance. Results: `runs/2026-10-29/QC/catalogues-20261106-SN2026aadx/` and
  `runs/2026-10-29/QC/catalogues-20261106-other-transients/`.
- NED returned sources for all 21 accepted fields. AllWISE returned sources
  for 18; three AllWISE queries failed. SDSS was unavailable for all 21 queries.
  The SDSS adapter has parser/fixture coverage but is **not verified against a
  successful live SDSS response in this run**.
- NED's NGC 1418 position lands on the visible galaxy in both SN2026aadx
  acquisitions. This is a field association, not an automatic host assignment.
- `runs/2026-10-28/index.html` and `runs/2026-10-29/index.html` show the current
  records, including failed frames and unavailable services. Existing reductions,
  reviewed C2/C3 choices and original QC figures remain unchanged.

References: [Astrometry.net](https://astrometry.net/doc/readme.html),
[NED API specification](https://ned.ipac.caltech.edu/Docs::API/),
[SDSS access tools](https://www.sdss4.org/dr17/data_access/tools/),
[IRSA AllWISE queries](https://irsa.ipac.caltech.edu/docs/program_interface/astropy_TAP.html),
[AllWISE column definitions](https://irsa.ipac.caltech.edu/data/WISE/docs/release/AllWISE/expsup/sec2_1a.html).
