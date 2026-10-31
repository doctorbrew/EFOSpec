"""Rebuild the editable SVG comparison from inspected reduction stages."""
from html import escape
from pathlib import Path


def render():
    parts = ['''<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="1040" viewBox="0 0 1120 1040" role="img" aria-labelledby="title description">
<title id="title">EFOSC2 reduction machinery: legacy IRAF and current PypeIt bridge</title>
<desc id="description">Two parallel reduction paths. Legacy uses IRAF tasks. The current pipeline uses custom archived calibration with PypeIt tracing, sky modelling and extraction. A local workbench supports manual anchors and separated two-source extraction.</desc>
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="#7c857e"/></marker></defs>
<style>text{font-family:'Avenir Next',Avenir,Arial,sans-serif;fill:#29362e}.title{font-family:Georgia,serif;font-size:29px;fill:#244d3d}.heading{font-size:21px;font-weight:600}.body{font-size:17px}.small{font-size:15px;fill:#536159}.label{font-size:13px;font-weight:600;letter-spacing:1px}.arrow{fill:none;stroke:#7c857e;stroke-width:1.5;marker-end:url(#arrow)}</style>
<rect width="1120" height="1040" rx="12" fill="#f7f6f0"/>
<text class="title" x="32" y="45">EFOSC2 reduction machinery</text>
<text class="small" x="32" y="72">Legacy task sequence and the implemented rapid migration — engine boundaries shown explicitly</text>
<rect x="340" y="94" width="440" height="54" rx="9" fill="#fffef9" stroke="#cbd3c8"/>
<text class="heading" x="560" y="128" text-anchor="middle">Science FITS + calibration references</text>
<path class="arrow" d="M420 148 V166 H288 V212"/><path class="arrow" d="M700 148 V166 H832 V212"/>
<text class="heading" x="48" y="195">Legacy PESSTO / IRAF</text>
<text class="heading" x="592" y="195">EFOSpec / rapid</text>''']
    left = [
        ('IRAF + LEGACY PYTHON', 'Prepare the detector image',
         'ccdproc: rapid trim; full mode can use bias + flat', 'Legacy wrappers select frames and preserve names'),
        ('IRAF + LEGACY PYTHON', 'Wavelength calibration',
         'identify / reidentify → fitcoords → transform', 'Legacy sky comparison adjusts the wavelength zero point'),
        ('IRAF', 'Trace, background, extraction',
         'apall: trace, aperture and background fitting', 'Weighted extraction / cleaning; interactive options'),
        ('IRAF + REFERENCE FILES', 'Flux calibration',
         'calibrate: sensitivity curve + extinction', 'standard / sensfunc can create a sensitivity curve'),
        ('LEGACY PYTHON + IRAF', 'Delivered products',
         'Legacy FITS / ASCII and product headers', 'Requires a configured IRAF + PyRAF installation'),
    ]
    right = [
        ('OUR PYTHON', 'Prepare the detector image',
         'Legacy rapid trim → gain conversion → spatial crop', 'No bias / flat / dark / overscan correction'),
        ('OUR PYTHON + ARCHIVED IRAF IDs', 'Wavelength calibration',
         '2D polynomial → 5577 / 6300 Å sky shift', '6364 Å is an independent check when measurable'),
        ('PYPEIT 1.14.0', 'Trace, sky, optimal + boxcar extraction',
         'FindObjects → global sky → Extract local joint fit', 'Fits neighbouring objects; exports one selected target'),
        ('OUR PYTHON + ARCHIVED RESPONSE', 'Flux calibration',
         'Archived sensitivity + La Silla extinction', 'No new sensitivity fit; no telluric correction'),
        ('PYPEIT + OUR PYTHON', 'Delivered products',
         'Native spec1d → air-grid legacy FITS / ASCII', 'Diagnostic figures + automatic Fieldnotes webpage'),
    ]
    for column, steps in enumerate((left, right)):
        x = 32 + 544*column
        for row, (owner, title, first, second) in enumerate(steps):
            y = 220 + 126*row
            fill = '#f6e9dd' if column == 0 else '#fffef9'
            if column == 1 and row == 2:
                fill = '#deeee3'
            parts.append(f'<rect x="{x}" y="{y}" width="512" height="108" rx="9" fill="{fill}" stroke="#cbd3c8"/>')
            for kind, dy, value in [('label', 21, owner), ('heading', 47, title),
                                     ('body', 72, first), ('small', 94, second)]:
                parts.append(f'<text class="{kind}" x="{x+16}" y="{y+dy}">{escape(value)}</text>')
            if row < 4:
                parts.append(f'<path class="arrow" d="M{x+256} {y+108} V{y+122}"/>')
    parts.extend(['''
<text class="small" x="32" y="861">The new route reads legacy reference files; it does not execute IRAF. Full calibration parity remains pending.</text>
<rect x="32" y="891" width="1056" height="111" rx="9" fill="#eef2f5" stroke="#6f8797" stroke-dasharray="6 4"/>
<text class="label" x="48" y="916">LOCAL EXTRACTION WORKBENCH</text>
<text class="heading" x="48" y="945">Manual anchors + sky → saved recipe → PypeIt → separate source spectra</text>
<text class="body" x="48" y="977">Separated traces in the saved detector window. Overlapping host subtraction needs a validated model.</text>
</svg>'''])
    return '\n'.join(parts)+'\n'


if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1]/'docs/figures/reduction-machinery.svg'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render())
    print(output)
