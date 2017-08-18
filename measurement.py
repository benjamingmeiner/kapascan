"""
This module combines the ``controller.py`` and ``table.py`` interfaces to a
single interface suited for raster measurements.

Class listing
-------------
Measurement :
    bla

Notes
-----
Context Manager

Example
-------
  >>>
  >>>
  >>>
"""
import sys
import itertools
from timeit import default_timer as timer
import time
import datetime
import threading
import logging
import numpy as np
from pprint import pformat as pretty
from . import controller
from . import table
from . import data_logger
from .base import ExceptionThread
from .helper import BraceMessage as __


logger = logging.getLogger(__name__)


class MeasurementError(Exception):
    """Simple exception class used for all errors in this module."""


class Measurement():
    """
    Blah Bli Blub

    Notes
    -----
    Context Manager

    Parameters
    ----------
    host : str
        The IP address of the controller.
    serial_port : str
        The serial port of the Arduino running grbl.
    settings : dict with keys:
        ``extent`` : tuple {((x0, x1, delta_x), (y0, y1, delta_y))
            The coordinates of the boundary points of the measuring area
            (x0, x1, y0, y1) and the step size of each axis (delta_x, delta_y)
        ``sampling_time`` : float, optional
            The desired sampling time in ms. Defaults to 0.256 ms.
        ``data_points`` : int, optional
            The number of data points to be acquired at each measurement
            position. Defaults to 100.
        ``mode`` : str {'absolute', 'relative'}, optional
            Sets the measuring area in relative or absolute coordinates.
            Defaults to 'absolute'.
        ``direction`` : tuple of str, optional
            Specifies the order and the direction in which the axes are moved.
            Defaults to ('x', 'y'). The two elements of the tuple set the
            'primary' and 'secondary' axis, where the primary axis is the axis
            that moves first and hence determines the principal scanning
            direction. Possible keys for the axis specification are 'x' and 'y',
            optionally prefixed with a sign that sets the direction,
            e.g. ('-y', 'x') for a scan in negative y-direction, starting at the
            minimal x value.
        ``change_direction`` : bool, optional
            Changes the primary scanning direction after each line. Defaults to
            True.

    Example
    -------
      >>>
      >>>
      >>>
    """

    def __init__(self, host_controller, serial_port, host_data_logger, settings):
        default_settings = {
            'sensors': ['2011'],
            'data_logger_channel': 101,
            'sampling_time': 0.256,
            'data_points': 50,
            'mode': 'absolute',
            'direction': ('x', 'y'),
            'change_direction': True
            }
        for key in settings:
            if key not in default_settings.keys() | {'extent'}:
                print("WARNING: invalid key: {}".format(key))
        if 'extent' not in settings:
            raise KeyError('extent')
        self.settings = {**default_settings, **settings}
        logger.info(__("Initialized measurement with settings:\n", self.settings, pretty=True))
        self._controller = controller.Controller(self.settings['sensors'],
                                                 host_controller)
        self._table = table.Table(serial_port)
        self._data_logger = data_logger.DataLogger(host_data_logger)
        self._saved_pos = None

    def connect(self):
        """
        Establishes all connections to the devices and performs some start up
        checks and a homing cycle if the current position is not known to grbl.
        """
        # TODO check if extent in accord with max travel, maybe via grbl
        # checker, "$C"?
        self._controller.connect()
        self._data_logger.connect()
        self._data_logger.configure(self.settings['data_logger_channel'])
        status = self._table.connect()
        if status.lower() == 'alarm':
            self._table.home()
        self._table.check_resolution(self.settings['extent'])

    def disconnect(self, *args):
        """Disconnects from all devices."""
        self._table.disconnect()
        self._data_logger.disconnect()
        self._controller.disconnect()

    def __enter__(self):
        try:
            self.connect()
            return self
        except BaseException as error:
            self.__exit__(*sys.exc_info())
            raise error

    __exit__ = disconnect

    @property
    def position(self):
        """Returns the current position."""
        return self._table.get_status()[1]

    def interactive_mode(self):
        """Starts the table's interactive mode."""
        feed = min(self._table.max_feed)
        self._table.serial_connection.command("G1 G90 F{}".format(feed))
        return self._table.interact()

    def move_away(self):
        """
        Moves the table to the outermost position. The previous position is
        preserved as an attribute, to be able to move back where you started.
        This function is useful to place the sample on the table without the
        sensor getting in the way.
        """
        self._saved_pos = self._table.get_status()[1]
        max_distance = (md - 0.1 for md in self._table.max_travel)
        self._table.move(*max_distance, mode='absolute')

    def move_back(self):
        """Moves the table back to the position stored by `move_away()`."""
        if self._saved_pos is not None:
            self._table.move(*self._saved_pos, mode='absolute')
        else:
            print("No position to move back to.")

    def move_to_start(self):
        """Moves the table to the starting position of the measurement."""
        self._table.move(self.settings['extent'][0][0],
                         self.settings['extent'][1][0], mode='absolute')

    def scan(self):
        """
        Rasters the measuring area. Halts at every measuring position and
        acquires a certain amount of data points (setting ``data_points``). The
        mean of this data sample is used as the data value at this position.
        Additionally, the temperature is measured at every measuring position.

        Returns
        -------
        x, y : 1D-array
            The vectors spanning the measuring area
        z, T : 2D-array
            The acquired data values at the respective coordinates
        """
        threads = []
        self._controller.set_sampling_time(self.settings['sampling_time'])
        self._controller.set_trigger_mode('continuous')

        x, y = self._vectors()
        positions = self._positions(x, y)
        length = len(positions)
        width = len(self.settings['sensors'])
        z = np.zeros((width, length))
        T = np.zeros(length)
        t = np.zeros(length)

        self._table.move(*positions[1][1], mode='absolute')
        logger.info(__("Started scan with {} positions.", length))
        for i, (i_pos, position) in _log_progress(list(enumerate(positions))):
            # --- Positioning and Display---
            threads.append(ExceptionThread(
                target=self._move_thread, name='move', args=(*position,)))
            threads.append(ExceptionThread(
                target=self._display_thread, name='display', args=(i, length)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            threads.clear()
            # --- Measurements ---
            t[i] = time.time()
            threads.append(ExceptionThread(
                target=self._get_z_thread, name='get_z', args=(z, i_pos)))
            threads.append(ExceptionThread(
                target=self._get_T_thread, name='get_T', args=(T, i_pos)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            threads.clear()

        z = z.reshape(width, len(x), len(y)).transpose(0, 2, 1)
        T = T.reshape((len(x), len(y))).transpose()
        logger.info("Finished scan.")
        return x, y, z, T, t

    def check_wipe(self):
        x_min_sample = self.settings['extent'][0][0]
        delta_x_sample = self.settings['extent'][0][1] - x_min_sample
        if x_min_sample < 16.5 + delta_x_sample:
            raise MeasurementError("Not enough space for complete wipe of the sample.")

    def wipe(self):
        # TODO: parametrize movement
        print("Wiping sample ...")
        pos = self.position
        xmax = self._table.max_travel[0]
        self._table.move(x=xmax)
        ywipe = pos[1] - 26
        if ywipe < 0:
            ywipe = 0
        self._table.move(y=ywipe)
        self._table.move(x=0)
        self._table.move(x=5)
        self._table.move(*pos)

    def _vectors(self):
        """
        Generates arrays with all absolute (x, y) values of the measuring area.
        In contrast to np.arange, the meauring range includes the stop value of
        the extent (x1 and y1) in any case.

        Returns
        -------
        vectors : list of arrays
            A list containing the x and y arrays.
        """
        if self.settings['mode'] == 'relative':
            position = self._table.get_status()[1]
        else:
            position = (0, 0)
        vectors = []
        for range_, offset in zip(self.settings['extent'], position):
            start, stop, step = range_
            if start == stop:
                vec = np.array([start], dtype=np.float)
            elif step >= stop - start:
                vec = np.array([start, stop], dtype=np.float)
            else:
                vec = np.arange(start, stop + 0.5 * step, step, dtype=np.float)
            vec += offset
            vectors.append(vec)
        return vectors

    def _positions(self, x, y):
        """
        Generates a list of all (x, y) positions of the measuring area in the
        order specified by the settings ``direction`` and ``change_direction``.

        Parameters
        ----------
        x, y : 1D array
            array of all coordinates along one axis

        Returns
        -------
        positions : list of 2-tuples
            A list of all (x, y) positions
        """
        def sort_key(enumerated_pair):
            """ Generates the keys for the sort function. """
            _, pair = enumerated_pair
            indices = {'x': 1, 'X': 1, 'y': 0, 'Y': 0}
            coeff = {'-': -1, '+': 1, ' ': 1, 'x': 1, 'X': 1, 'y': 1, 'Y': 1}
            first_axis, second_axis = self.settings['direction']
            keys = [pair[indices[first_axis[-1]]] * coeff[second_axis[0]],
                    pair[indices[second_axis[-1]]] * coeff[first_axis[0]]]
            return keys

        positions = list(enumerate(itertools.product(x, y)))
        positions.sort(key=sort_key)
        if self.settings['change_direction']:
            if self.settings['direction'][0][-1] in 'xX':
                line_len = len(x)
            elif self.settings['direction'][0][-1] in 'yY':
                line_len = len(y)
            # group positions by line
            lines = list(zip(*[positions[i::line_len] for i in range(line_len)]))
            # reverse every second line in-place:
            lines[1::2] = [line[::-1] for line in lines[1::2]]
            positions = list(itertools.chain(*lines))
        return positions

    def _display_thread(self, i, length):
        """
        The target function of the thread showing the measurement status
        at the data logger display.
        """
        counter = "{i: >{width:}}/{length:}".format(
            i=i + 1, width=len(str(length)), length=length)
        counter = counter.rjust(13)
        self._data_logger.display(counter)

    def _move_thread(self, x, y):
        """The target function of the thread moving the table."""
        self._table.move(x, y, 'absolute')

    def _get_z_thread(self, z, i_pos):
        """The target function of the thread acquiring the z values."""
        z[:, i_pos] = self._controller.acquire(self.settings['data_points']).mean(1)

    def _get_T_thread(self, T, i_pos):
        """The target function of the thread acquiring the temperature."""
        T[i_pos] = self._data_logger.get_data()


def _format_remaining(seconds):
    """
    Formats a timedelta object to only show the seconds without the decimal
    places.
    """
    if seconds == "?":
        return "?"
    delta = str(datetime.timedelta(seconds=seconds + 0.5))
    return delta[:-7]


def _log_progress(sequence, every=1, size=None, name='Position', timeit=True):
    from ipywidgets import IntProgress, HTML, VBox, HBox
    from IPython.display import display
    progress_logger = logging.getLogger(__name__ + ".progress")

    is_iterator = False
    if size is None:
        try:
            size = len(sequence)
        except TypeError:
            is_iterator = True
            timeit = False
    if size is not None:
        if every is None:
            if size <= 200:
                every = 1
            else:
                every = int(size / 200)     # every 0.5%
    else:
        assert every is not None, 'sequence is iterator, set every'

    if is_iterator:
        progress = IntProgress(min=0, max=1, value=1)
        progress.bar_style = 'info'
    else:
        progress = IntProgress(min=0, max=size, value=0)
    position_label = HTML()
    time_label = HTML()
    label = HBox(children=[position_label, time_label])
    box = VBox(children=[label, progress])
    display(box)

    index = 0
    if timeit:
        t_remaining = "?"
        t_start = timer()
    try:
        for index, record in enumerate(sequence, 1):
            if index == 1 or index % every == 0:
                if is_iterator:
                    position_label.value = u'{}: {} / ?'.format(name, index)
                else:
                    progress.value = index
                    position_label.value = u'{}: {} / {}'.format(name, index, size)
                    if timeit:
                        time_label.value =  u' | Remaining: {}'.format(_format_remaining(t_remaining))
            progress_logger.info(position_label.value + time_label.value)
            yield record
            if timeit:
                t_remaining = (size - index - 1) * (timer() - t_start) / (index)
    except:
        progress.bar_style = 'danger'
        raise
    else:
        progress.bar_style = 'success'
        progress.value = index
        position_label.value = "{}: {}".format(name, str(index or '?'))
