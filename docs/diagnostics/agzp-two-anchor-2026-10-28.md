# AT2026agzp: explicit two-anchor recovery

- Observing night: **2026-10-28**; exposure `EFOSC.2026-10-29T04:00:57.903.fits`, Gr11/Free/slit1.0, 1800 s.
- The response was available. The original flux export was withheld by the independent 6363 Å wavelength check, not by a missing standard.
- The user explicitly accepted cross-checking 5577 and 6300 Å. New native manual replays expose `--sky-validation two-anchor`; the existing three-line default remains available and unchanged.
- Fresh offsets: −5.106686 and −4.889584 Å; disagreement 0.217103 Å, applied mean −4.998135 Å. Both anchors pass the existing SNR, width and centroid-error checks. Agreement must remain within 3 Å and the shift within 20 Å.
- The 6363 Å residual remains **−4.164518 Å, diagnostic failed**. It is measured and retained, not claimed to pass. FITS records `WAVEPOL=two-anchor`, `WAVEVAL=T`, `SKY6363=F`; manifests and ASCII identify the policy.
- Fresh raw calibration processing, bounded PypeIt extraction and same-night VMa2 response produced a separate flux spectrum. The aperture radius remains 6.25 pixels. Explicit fixed raw background bands `[510,535)` and `[571,596)` come from the previous middle-row geometry; the earlier trace-following mask was not silently reused.
- All 855 extraction rows retain two-sided support, at least 16 accepted pixels per side; background reduced χ² 0.950. Valid exported flux fraction: 95.90%. This does not establish host deblending or background covariance.
- Fresh telluric fits: 12 standards, 14 independent transfers; 114 corrected samples in qualified O₂ B and H₂O 7200 bands. This exposure passes the existing time/airmass transfer gates. Uncorrected FITS/ASCII, masks, statistical uncertainty and transfer variance are retained. Absolute flux remains unvalidated.
- Six current science spectra are now displayed: four original native deliveries plus separately selected SN2026ayt and AT2026agzp recoveries. AT2026agvs still fails anchor agreement; SN2026abgb still lacks an accepted uncontaminated background. Earlier failures/counts remain archived and visible.
- Evidence: `runs/2026-10-28/nightly/20261113T141208Z-6fee4b/QC/agzp-two-anchor-20261113T174807Z/` contains the recipe, raw/source hashes, fresh extraction, telluric transfers, redshift checks, plots, standalone HTML and verification. No earlier scientific products were overwritten.
