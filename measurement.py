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
import threading
import datetime
import numpy as np
from . import controller
from . import table
from . import logger


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
            'primary' and 'secondary'axis, where the primary axis is the axis
            that determines the principal scanning direction.
            Possible keys for the axis specification are 'x' and 'y', optionally
            prefixed with a sign the sets the direction, e.g. ('-y', 'x') for a
            scan in negative y-direction, starting at the minimal x value.
        ``change_direction`` : bool, optional
            Changes the primary scanning direction after each line. Defaults to
            True.

    Example
    -------
      >>>
      >>>
      >>>
    """

    def __init__(self, host_controller, serial_port, host_logger, settings):
        self._controller = controller.Controller(settings['sensors'], host_controller)
        self._table = table.Table(serial_port)
        self._logger = logger.Logger(host_logger)
        default_settings = {
            'sensors': ['2011'],
            'logger_channel': 101,
            'sampling_time': 0.256,
            'data_points': 100,
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
        self._saved_pos = None

    def __enter__(self):
        try:
            return self.initialize()
        except BaseException as error:
            self.__exit__(*sys.exc_info())
            raise error

    def __exit__(self, *args):
        self.stop()

    def initialize(self):
        """
        Establishes all connections to the devices and performs some start up
        checks and a homing cycle if the current position is not known to grbl.
        """
        # TODO check if extent in accord with max travel, maybe via grbl
        # checker, "$C"?
        self._controller.connect()
        self._logger.connect()
        self._logger.configure(self.settings['logger_channel'])
        status = self._table.connect()
        if status.lower() == 'alarm':
            print("Homing ...")
            self._table.home()
        self._table.check_resolution(self.settings['extent'])
        return self

    def stop(self):
        """Disconnects from all devices."""
        self._table.disconnect()
        self._logger.disconnect()
        self._controller.disconnect()

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
        z = np.zeros(length)
        T = np.zeros(length)

        t_start = timer()
        for i, (i_pos, position) in enumerate(positions):
            # TODO test perforontrollemance of single threads (sleeps in targets usw)
            # TODO compare to non threaded scan
            # --- Positioning and Display---
            threads.append(threading.Thread(
                target=self._display_thread, name='display', args=(i, length)))
            threads.append(threading.Thread(
                target=self._move_thread, name='move', args=(*position,)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            threads.clear()
            # --- Measurements ---
            threads.append(threading.Thread(
                target=self._get_z_thread, name='get_z', args=(z, i_pos)))
            threads.append(threading.Thread(
                target=self._get_T_thread, name='get_T', args=(T, i_pos)))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            threads.clear()
            t_remaining = (length - i) * (timer() - t_start) / (i + 1)
            print("remaining: {}".format(_format_remaining(t_remaining)))

        z = np.transpose(z.reshape((len(x), len(y))))
        T = np.transpose(T.reshape((len(x), len(y))))
        return x, y, z, T

    def _vectors(self):
        """
        Generates arrays with all absolute (x, y) values of the measuring area.
        In contrast to np.arange, the stop value of the extent (x1 and y1) is
        included in any  case.

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
            coeff = {'-': -1, '+': 1, ' ': 1, 'x': 1, 'y': 1}
            first_axis, second_axis = self.settings['direction']
            keys = [pair[indices[first_axis[-1]]] * coeff[second_axis[0]],
                    pair[indices[second_axis[-1]]] * coeff[first_axis[0]]]
            return keys

        positions = list(enumerate(itertools.product(x, y)))
        positions.sort(key=sort_key)
        if self.settings['change_direction']:
            if self.settings['direction'][0] == 'x':
                line_len = len(y)
            elif self.settings['direction'][0] == 'y':
                line_len = len(x)
            # group positions by line
            lines = list(zip(*[positions[i::line_len] for i in range(line_len)]))
            # reverse every second line in-place:
            lines[1::2] = [line[::-1] for line in lines[1::2]]
            positions = list(itertools.chain(*lines))
        return positions

    def _display_thread(self, i, length):
        """
        The target function of the thread showing the measurement status
        at the logger display.
        """
        counter = "{i: >{width:}}/{length:}".format(
            i=i + 1, width=len(str(length)), length=length)
        counter = counter.rjust(13)
        self._logger.display(counter)

    def _move_thread(self, x, y):
        """The target function of the thread moving the table."""
        self._table.move(x, y, 'absolute')

    def _get_z_thread(self, z, i_pos):
        """The target function of the thread acquiring the z values."""
        self._controller.start_acquisition(self.settings['data_points'])
        z[i_pos] = self._controller.stop_acquisition().mean()

    def _get_T_thread(self, T, i_pos):
        """The target function of the thread acquiring the temperature."""
        T[i_pos] = self._logger.get_data()


def _format_remaining(seconds):
    """
    Formats a timedelta object to only show the seconds without the decimal
    places.
    """
    delta = str(datetime.timedelta(seconds=seconds + 0.5))
    return delta[:-7]

