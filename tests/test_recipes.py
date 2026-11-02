"""Manual selections use native detector pixels and bind to immutable inputs."""
from copy import deepcopy
import unittest

import numpy as np

from efospec.recipes import DetectorWindow, validate_recipe, sky_mask


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.window = DetectorWindow((200, 141), (4, 99))
        self.inputs = {'raw': 'a'*64, 'images': 'b'*64, 'manifest': 'c'*64}
        self.recipe = {'schema_version': 1, 'engine_version': '1.14.0',
                       'coordinates': 'raw_detector_pixels_zero_based',
                       'input_sha256': dict(self.inputs), 'source_mode': 'manual',
                       'objects': [{'id': 'primary', 'label': 'SNtest', 'kind': 'point',
                                    'spec': 104., 'spat': 140., 'fwhm': 3., 'radius': 6.}],
                       'sky': {'mode': 'regions', 'include': [[100., 130.], [160., 230.]],
                               'exclude': [[175., 185.]]}}

    def test_detector_coordinates_round_trip_without_binning_twice(self):
        self.assertEqual(self.window.to_local(104.25, 140.5), (100.25, 41.5))
        self.assertEqual(self.window.to_raw(100.25, 41.5), (104.25, 140.5))

    def test_background_regions_and_exclusions_change_the_actual_mask(self):
        before = deepcopy(self.recipe)
        recipe = validate_recipe(self.recipe, self.window, self.inputs)
        mask = sky_mask(recipe, self.window)
        self.assertEqual(mask.shape, (200, 141))
        self.assertTrue(mask[:, 11].all())  # raw spatial pixel 110
        self.assertFalse(mask[:, 81].any())  # excluded raw pixel 180
        self.assertFalse(mask[:, 41].any())  # selected source at raw pixel 140
        self.assertFalse(mask[:, [0, -1]].any())  # off-slit boundary columns
        self.assertEqual(self.recipe, before)

    def test_recipe_cannot_be_replayed_on_changed_inputs(self):
        changed = dict(self.inputs, raw='d'*64)
        with self.assertRaisesRegex(ValueError, 'input'):
            validate_recipe(self.recipe, self.window, changed)

    def test_invalid_apertures_positions_and_labels_are_rejected(self):
        for key, value in [('radius', -1.), ('fwhm', float('nan')), ('spec', 999.),
                           ('spat', 100.), ('id', '../escape'), ('label', r'\input{file}')]:
            with self.subTest(key=key, value=value):
                recipe = deepcopy(self.recipe)
                recipe['objects'][0][key] = value
                with self.assertRaises(ValueError):
                    validate_recipe(recipe, self.window, self.inputs)

    def test_two_well_separated_sources_have_distinct_stable_ids(self):
        recipe = deepcopy(self.recipe)
        recipe['objects'].append(dict(recipe['objects'][0], id='host', label='Host',
                                      spat=200., kind='galaxy'))
        result = validate_recipe(recipe, self.window, self.inputs)
        self.assertEqual([o['id'] for o in result['objects']], ['primary', 'host'])
        recipe['objects'][1]['spat'] = 145.
        with self.assertRaisesRegex(ValueError, 'separated'):
            validate_recipe(recipe, self.window, self.inputs)

    def test_empty_background_and_ignored_automatic_edits_are_not_accepted(self):
        recipe = deepcopy(self.recipe)
        recipe['sky']['include'] = []
        with self.assertRaisesRegex(ValueError, 'sky|background'):
            validate_recipe(recipe, self.window, self.inputs)
        recipe = deepcopy(self.recipe)
        recipe['source_mode'] = 'automatic'
        with self.assertRaisesRegex(ValueError, 'automatic'):
            validate_recipe(recipe, self.window, self.inputs)

    def test_polynomial_recipe_requires_two_sided_samples_and_explicit_order(self):
        recipe=deepcopy(self.recipe)
        recipe['sky'].update(mode='polynomial',degree=2,sigma_clip=4.)
        checked=validate_recipe(recipe,self.window,self.inputs)
        self.assertEqual(checked['sky']['degree'],2)
        recipe['sky']['include']=[[100.,130.]]
        with self.assertRaisesRegex(ValueError,'each side'):
            validate_recipe(recipe,self.window,self.inputs)
        recipe['sky']['include']=[[100.,130.],[160.,230.]]
        recipe['sky']['degree']=8
        with self.assertRaisesRegex(ValueError,'degree'):
            validate_recipe(recipe,self.window,self.inputs)
        for invalid in (None,[], 'polynomial',2):
            recipe['sky']=invalid
            with self.assertRaisesRegex(ValueError,'sky selection'):
                validate_recipe(recipe,self.window,self.inputs)
