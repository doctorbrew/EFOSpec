"""Render delayed native Qt redraws with the same typography as saved figures."""
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .figure_style import house_style


class ScientificCanvas(FigureCanvasQTAgg):
    # Qt schedules draw_idle after the plotting function's rc_context exits.
    # TeX resolves its font family at render time, so style that render too.
    @house_style
    def draw(self):
        return super().draw()

    @house_style
    def print_figure(self,*args,**kwargs):
        return super().print_figure(*args,**kwargs)
