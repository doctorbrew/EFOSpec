import matplotlib.pyplot as plt
import numpy as np
from efospec.acquisition_slit import draw_slit_orientation


def test_documented_direction_does_not_assign_a_slit_position():
    fig, ax = plt.subplots()
    data = np.arange(100).reshape(10, 10)
    ax.imshow(data, origin='lower')
    limits = ax.get_xlim(), ax.get_ylim()
    metadata = draw_slit_orientation(ax)
    assert metadata['detector_axis'] == 'x'
    assert metadata['detector_angle_deg'] == 0
    assert metadata['slit_center_y'] is None
    assert not metadata['on_slit_confirmed']
    assert (ax.get_xlim(), ax.get_ylim()) == limits
    np.testing.assert_array_equal(ax.images[0].get_array(), data)
    assert not ax.lines  # No line at an invented detector row.
    assert len(ax.artists) == 1
    plt.close(fig)
