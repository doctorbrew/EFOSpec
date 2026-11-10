"""Explain implementation coverage separately from calibration availability.

These are code-path capabilities, not a certificate for an exposure. Actual
masters, sky checks, references and response coverage must still be validated.
"""


def archive_setup_issue(setup):
    """The archive bridge's existing setup gate, with an actionable reason."""
    grism, filter_name = setup.get('grism'), setup.get('filter')
    if setup.get('binx') != 2 or setup.get('biny') != 2:
        return 'Archive reduction requires the inspected 2x2 detector binning.'
    if grism == 'Gr16' and filter_name == 'OG530':
        return ('Gr16/OG530 is not enabled in the archive reduction: reduce-red provides experimental review counts, '
                'while red-sky flexure validation and a matching flux response are still required for science delivery.')
    if grism in {'Gr11', 'Gr13'} and filter_name == 'GG495':
        return (f'{grism}/GG495 is not enabled in the archive reduction: the filtered '
                'native extraction and response need validation and nightly integration.')
    if grism not in {'Gr11', 'Gr13'} or filter_name != 'Free':
        return (f'Archive reduction does not enable {grism}/{filter_name}; '
                'only Gr11/Gr13 with the Free filter are implemented.')
    return None


def setup_support(setup):
    """Describe existing routes without opening files or accepting calibrations."""
    grism, filter_name = setup.get('grism'), setup.get('filter')
    binned = setup.get('binx') == setup.get('biny') == 2
    optical = grism in {'Gr11', 'Gr13'} and filter_name in {'Free', 'GG495'}
    red = grism == 'Gr16' and filter_name == 'OG530'
    masters = binned and (optical or red)
    paired = binned and optical and setup.get('slit') in {'slit1.0', 'slit1.5'}
    issue = archive_setup_issue(setup)
    development = []
    if not masters:
        development.append('Implement and validate native detector geometry and raw wavelength calibration for this setup.')
    if red:
        development.extend([
            'Use reduce-red for native Gr16/OG530 review counts with propagated variance; these are not accepted science products.',
            'Validate red-sky flexure with held-out features; 5577 A is outside Gr16 coverage. Existing correlation is diagnostic only.',
            'Register the observed standard against a physical flux reference and validate an OG530 response.',
            'Measure red fringing and define supported wavelength/telluric masks.',
        ])
    elif optical and filter_name == 'GG495':
        development.extend([
            ('Use reduce-filtered for separate experimental Gr13/GG495 standard counts; validate physical references and responses.'
             if grism == 'Gr13' else 'Validate the existing experimental native extraction and response on filtered standards.'),
            'Measure the usable filter band from the data; do not substitute the Free-filter response.',
            'Retain matched Free/GG495 standard observations for a separately validated second-order correction.',
        ])
    elif not paired:
        development.append('Implement and validate the paired native extraction for this grism, filter, binning and slit.')
    if issue:
        development.append('Integrate accepted native products into the dated nightly workflow with explicit calibration provenance.')
    return {
        'archive_bridge': 'enabled' if issue is None else 'not_enabled',
        'archive_issue': issue,
        'native_masters': 'experimental' if masters else 'not_enabled',
        'native_pair': 'experimental' if paired else 'not_enabled',
        'separate_filtered_standards': 'experimental' if paired and grism == 'Gr13' and filter_name == 'GG495' else 'not_enabled',
        'red_counts_diagnostic': 'experimental' if binned and red and setup.get('slit') in {'slit1.0','slit1.5'} else 'not_enabled',
        'scientifically_validated': False,
        'development_required': development,
        'validation_required': [
            'Verify selected raw inputs and master hashes, wavelength coverage and exposure-specific sky checks.',
            'Verify standard identity, physical reference, response coverage and independent flux/uncertainty checks.',
            'Retain source-identification and bounded two-sided background checks.',
        ],
    }
