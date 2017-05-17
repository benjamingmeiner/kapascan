import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
from skimage.measure import profile_line
import numpy as np
from functools import partial


def plot(x, y, z, contour=True):
    xis1D = True if x.shape[0] is 1 else False
    yis1D = True if y.shape[0] is 1 else False
    if xis1D and yis1D:
        pass
    elif xis1D and not yis1D:
        return _plot1D(y, np.transpose(z)[0], "$y$ [mm]", "z [µm]")
    elif yis1D and not xis1D:
        return _plot1D(x, z[0], "$x$ [mm]", "$z$ [µm]")
    else:
        return _plot2D(x, y, z)


def _plot1D(x, y, xlabel, ylabel): 
    fig, ax = plt.subplots()
    ax.plot(x, y)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    plt.show(block=False)
    return fig


def _extent(x, y):
    """
    Calculates extent values to be used by imshow()

    Parameters
    ----------
    x, y : 1D-arrays
        The vectors spanning the measurment area

    Returns
    -------
    extent : tuple
        The extent values
    """
    dx = (x[-1] - x[0]) / (2 * len(x))
    dy = (y[-1] - y[0]) / (2 * len(y))
    
    if dx == 0 and dy == 0:
        dx, dy = 1, 1
    else:
        if dx == 0:
            dx = dy
        if dy == 0:
            dy = dx
    return (x[0] - dx, x[-1] + dx, y[0] - dy, y[-1] + dy)


def _plot2D(x, y, z, contour=False): 
    ext = _extent(x, y)
    fig, ax = plt.subplots()
    if contour:
        ax.contour(z, colors='k', extent=ext, linewidths=0.5)
    image = ax.imshow(z, origin='lower', extent=ext, aspect='equal', picker=True)
    cbar = fig.colorbar(image)
    tick_step = [int(np.ceil(len(c) / 11)) for c in [x, y]]
    ax.set_xticks(x[::tick_step[0]])
    ax.set_yticks(y[::tick_step[1]])
    cbar.set_ticks(np.linspace(z.min(), z.max(), 8))
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_title("Surface")
    cbar.set_label("z [µm]")
    
    profile = _ProfileBuilder(fig, ax, x, y, z)
    profile.connect()
    plt.show(block=False)
    return fig


def _plot_profile(x, y, z, src, dst):
    xextent = x[-1] - x[0]
    yextent = y[-1] - y[0]
    src_pixel = [0, 0]
    dst_pixel = [0, 0]
    src_pixel[0] = len(y) * (src[1] - y[0]) / yextent
    src_pixel[1] = len(x) * (src[0] - x[0]) / xextent
    dst_pixel[0] = len(y) * (dst[1] - y[0]) / yextent
    dst_pixel[1] = len(x) * (dst[0] - x[0]) / xextent
    z_profile = profile_line(z, src_pixel, dst_pixel, linewidth=1, order=1, mode='nearest')

    fig, ax1 = plt.subplots()
    x_profile = np.linspace(src[0], dst[0], len(z_profile))
    ax1.plot(x_profile, z_profile, color=(0.7, 0.1, 0))
    
    ax2 = ax1.twiny()
    lim1 = list(sorted([src[0], dst[0]]))
    lim2 = list(sorted([src[1], dst[1]]))
    ax1.set_xlim(lim1)
    ax2.set_xlim(lim2)
    ax1.set_xticks(np.linspace(ax1.get_xbound()[0], ax1.get_xbound()[1], 8))
    ax2.set_xticks(np.linspace(ax2.get_xbound()[0], ax2.get_xbound()[1], 8))
    ax1.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
    ax2.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
    ax1.set_xlabel("$x$ [mm]")
    ax2.set_xlabel("$y$ [mm]")
    ax1.set_ylabel("$z$ [µm]")
    ax1.set_title("Profile Line", y=1.12)
    ax1.grid()
    plt.show(block=False)
    return fig


class _ProfileBuilder(object):
    def __init__(self, fig, ax, x, y, z):
        self.x = x
        self.y = y
        self.z = z
        self.fig = fig
        self.ax = ax
        self.src = None
        self.dst = None
        self.pressed = False

    def connect(self):
        self.id_press = self.fig.canvas.mpl_connect(
            'button_press_event', partial(self, 'press'))
        self.id_release = self.fig.canvas.mpl_connect(
            'button_release_event', partial(self, 'release'))
        self.id_motion = self.fig.canvas.mpl_connect(
            'motion_notify_event', partial(self, 'motion'))
        
    def __call__(self, what, event):
        if what == 'press':
            self.on_press(event)
        elif what == 'release':
            self.on_release(event)
        elif what == 'motion':
            self.on_motion(event)

    def on_press(self, event):
        if event.inaxes != self.ax:
            return
        if event.button != 2:
            return
        self.src = event.xdata, event.ydata
        self.pressed = True
        self.line, = self.ax.plot(self.src[0], self.src[1], color=(0.7, 0.1, 0))

    def on_motion(self, event):
        if not self.pressed:
            return
        x = [self.src[0], event.xdata]
        y = [self.src[1], event.ydata]
        self.line.set_ydata(y)
        self.line.set_xdata(x)
        self.fig.canvas.draw()
        
    def on_release(self, event):
        if not self.pressed:
            return
        if event.xdata != None and event.ydata != None:
            self.dst = event.xdata, event.ydata
            _plot_profile(self.x, self.y, self.z, self.src, self.dst)
        self.pressed = False
