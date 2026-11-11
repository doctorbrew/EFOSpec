"""House-style catalogue positions on the unchanged acquisition pixels."""
from pathlib import Path

from .figure_style import house_style, save_qc, style
from .field_catalogues import galaxy_labels, redshift_label

GALAXY_COLOR = '#ff8080'


def place_labels(fig):
    """Place tags beside markers, with clear space around all text and dots."""
    from matplotlib.text import Annotation, Text
    from matplotlib.transforms import Bbox
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    point = fig.dpi / 72
    for ax in fig.axes:
        labels = [label for label in ax.texts if isinstance(label, Annotation)]
        markers = []
        for collection in ax.collections:
            for xy in collection.get_offsets():
                x, y = ax.transData.transform(xy)
                if ax.bbox.contains(x, y):
                    markers.append(Bbox.from_extents(x-8*point, y-8*point,
                                                     x+8*point, y+8*point))
        placed = [artist.get_window_extent(renderer).padded(3*point)
                  for artist in ax.artists if artist.get_gid()=='efosc2-slit-orientation']
        for label in labels:
            preferred = -1 if label.get_position()[0] < 0 else 1
            line_step = label.get_fontsize() * 1.6
            steps = int(ax.bbox.height / (line_step*point)) + 1
            offsets = [0] + [sign*i*line_step for i in range(1, steps+1) for sign in (1,-1)]
            found = False
            for dy in offsets:
                for side in (preferred, -preferred):
                    label.set_position((side*12, dy))
                    label.set_ha('right' if side < 0 else 'left')
                    label.set_va('center')
                    label.update_positions(renderer)
                    box = Text.get_window_extent(label, renderer).padded(3*point)
                    inside = ax.bbox.contains(box.x0,box.y0) and ax.bbox.contains(box.x1,box.y1)
                    if inside and not any(box.overlaps(other) for other in markers+placed):
                        placed.append(box)
                        found = True
                        break
                if found:
                    break
            if not found:
                raise ValueError('No non-overlapping side placement for '+label.get_text())


@house_style
def plot_catalogue_field(data, field, output):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from .recovery_qc import _image
    from .acquisition_slit import draw_slit_orientation
    ny, nx = data.shape
    galaxies = [s for s in field['sources'] if s['galaxy_candidate']]
    labels = galaxy_labels(field['sources'])
    ncol = min(3, max(1, len(galaxies)))
    legend_rows = (len(galaxies) + ncol - 1) // ncol
    legend_height = 2.0 + .42 * legend_rows
    height = 9 + legend_height
    fig, axes = plt.subplots(1, 2, figsize=(20, height))
    fig.subplots_adjust(left=.075, right=.98, bottom=legend_height/height,
                        top=1-1.1/height, wspace=.28)
    half = min(180, nx/2, ny/2)
    bounds = [(-.5,nx-.5,-.5,ny-.5), (nx/2-half,nx/2+half,ny/2-half,ny/2+half)]
    for ax, limits, title in zip(axes, bounds, ['Acquisition field', 'Detector-centre zoom']):
        _image(ax, data).set_cmap('gray_r')
        for catalogue, marker in [('NED','o'),('SDSS','s')]:
            rows = [r for r in field['sources'] if r['catalogue']==catalogue
                    and r['galaxy_candidate']]
            if rows:
                ax.scatter([r['x'] for r in rows], [r['y'] for r in rows], s=100,
                    marker=marker, facecolors='none', edgecolors=[GALAXY_COLOR], linewidths=1.8)
            for row in rows:
                if row['galaxy_candidate'] and limits[0]<row['x']<limits[1] and limits[2]<row['y']<limits[3]:
                    near_right = row['x'] > (limits[0]+limits[1])/2
                    label = labels[row['id']]
                    ax.annotate(label, (row['x'],row['y']), xytext=(-12 if near_right else 12,0), textcoords='offset points',
                        ha='right' if near_right else 'left',
                        va='center',
                        color=GALAXY_COLOR, fontsize=15, clip_on=True)
        ax.set(xlim=limits[:2], ylim=limits[2:], xlabel='Acquisition x pixel', ylabel='Acquisition y pixel', title=title)
    field['slit_orientation'] = draw_slit_orientation(axes[1])
    catalogues = list(dict.fromkeys(s['catalogue'] for s in galaxies))
    legend_title = ' / '.join(catalogues or ['NED']) + ' galaxy candidates'
    handles = [Line2D([], [], linestyle='none', marker='o' if s['catalogue']=='NED' else 's',
                      markerfacecolor='none', markeredgecolor=GALAXY_COLOR,
                      markeredgewidth=1.8, markersize=10,
                      label=labels[s['id']]+': '+redshift_label(s)) for s in galaxies]
    style.styled_legend(fig, handles=handles, title=legend_title, title_fontsize=20,
                        ncol=ncol, loc='lower center', bbox_to_anchor=(.5,.5/height),
                        columnspacing=1.3)
    astrometry = field['astrometry']
    fig.suptitle(field['object']+' / Potential host galaxies\n'+Path(field['raw']).name, fontsize=20)
    fig.text(.5,.015,f"Astrometry: {astrometry['matched_stars']} matched stars; RMS {astrometry['rms_pixel']:.2f} pixels. "
             'Catalogue positions only; host association unconfirmed.', ha='center',fontsize=14)
    place_labels(fig)
    save_qc(fig, output, 'catalogues', field['object'])
    plt.close(fig)
