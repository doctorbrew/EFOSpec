"""Read-only raw-calibration readiness, with no IRAF files or archive fallback.

This is a preflight report, not a native reduction implementation. Candidate
standard exposures still need independent reference matching and flux fitting.
"""
from .planning import RAW_ROLES, _select, validate_frame
from .setup_support import setup_support


def assess_native_readiness(inventory):
    raw = [f for f in inventory['frames'] if f['role'] in RAW_ROLES
           and 'duplicate_of' not in f]
    ignored = [f['path'] for f in inventory['frames'] if f['role'] == 'processed']
    invalid = [{'path': f['path'], 'issues': validate_frame(f)} for f in raw if validate_frame(f)]
    invalid.extend({'path': f['path'], 'issues': [f['role'], *f['issues']]}
                   for f in inventory['frames'] if f['role'].startswith('review_')
                   and 'duplicate_of' not in f)
    blockers = []
    if inventory['errors'] or inventory['identity_conflicts'] or invalid:
        blockers.append('Resolve invalid raw metadata, unreadable inputs, and conflicting identities.')
    exposures = []
    if not blockers:
        targets = [f for f in raw if f['role'] in {'science', 'standard_candidate'}]
        for target in targets:
            selected = {role: _select(target, [f for f in raw if f['role'] == role], role)
                        for role in ('arc', 'bias', 'flat')}
            if target['role'] == 'science':
                selected['standard_candidate'] = _select(
                    target, [f for f in raw if f['role'] == 'standard_candidate'], 'standard')
                selected['standard_candidate']['policy'] = (
                    'nearest same-night raw standard candidate in identical setup; '
                    'identity and physical reference not yet verified')
            for role, selection in selected.items():
                if selection['status'] != 'selected':
                    blockers.append(f"{role} {selection['status']}: {target['path']}")
            exposures.append({'path': target['path'], 'setup': target['setup'],
                              'raw_calibrations': selected,
                              'pipeline_support': setup_support(target['setup'])})
        if not targets:
            blockers.append('No usable raw science or standard exposures.')
    complete = not blockers
    blockers.extend([
        'Experimental native masters and wavelength fits require per-group calibration and independent science validation; run calibrate-native. No IRAF IDs or processed arcs may substitute.',
        'Standard identities and independent physical flux references must be matched; sensitivity must be derived from the supplied observations.',
        'This preflight checks candidate availability only; execute reduce-native and inspect its scientific validation before accepting products.',
    ])
    return {'schema_version': 1, 'calibration_policy': 'native_only',
            'iraf_runtime_required': False, 'iraf_calibration_products_allowed': False,
            'processed_inputs_ignored': ignored, 'invalid_inputs': invalid,
            'calibration_tests_ignored': [f['path'] for f in inventory['frames']
                                          if f['role'] == 'flat_test'],
            'input_errors': inventory['errors'], 'identity_conflicts': inventory['identity_conflicts'],
            'exposures': exposures, 'raw_candidates_complete': complete,
            'native_calibration_execution_implemented': True,
            'native_execution_implemented': True, 'reduction_ready': False,
            'blockers': blockers}
