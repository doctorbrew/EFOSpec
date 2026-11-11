"""Documented EFOSC2 slit direction on unrotated acquisition pixels."""

MANUAL_URL = ('https://www.eso.org/sci/facilities/lasilla/instruments/efosc/'
              'doc/manual/EFOSC2manual_v4.2.pdf')


def draw_slit_orientation(ax):
    """Add a direction key, without assigning an undocumented slit centre row.

    Manual section 3.1.3 / Figure 17 puts the slit along CCD x. The rotator
    changes its sky PA, not its direction on the raw detector. Section 3.5.4
    says slit y is measured separately and stored in the instrument database.
    This key uses display coordinates and must not be used on a rotated image.
    """
    from matplotlib.offsetbox import AnchoredOffsetbox, DrawingArea, TextArea, VPacker
    from matplotlib.patches import FancyArrowPatch
    from .figure_style import COLORS

    direction = DrawingArea(190, 18, 0, 0)
    direction.add_artist(FancyArrowPatch((8, 9), (182, 9), arrowstyle='<->',
                         mutation_scale=19, linewidth=3, color=COLORS[1]))
    label = TextArea('Slit direction (CCD x)', textprops={'fontsize':20, 'color':'black'})
    key = AnchoredOffsetbox(loc='upper right',
        child=VPacker(children=[label, direction], align='center', pad=0, sep=3),
        frameon=True, pad=.4, borderpad=.6)
    key.patch.set(facecolor='white', edgecolor='none', alpha=.9)
    key.set_gid('efosc2-slit-orientation')
    key.set_zorder(10)
    ax.add_artist(key)
    return dict(kind='orientation_only', detector_axis='x', detector_angle_deg=0.,
                slit_center_y=None, on_slit_confirmed=False,
                source=MANUAL_URL, source_sections=['3.1.3 / Figure 17', '3.5.4'])
