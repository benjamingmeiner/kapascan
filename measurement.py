"""
This module combines the ``controller.py`` and ``table.py`` interfaces to a
single interface suited for raster measurements.

Class listing
-------------
Measuremtent :
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
import controller
import table
import itertools
import numpy as np
from timeit import default_timer as timer
import datetime


class MeasurementError(Exception):
    """Simple exception class used for all errors in this module."""


class InvalidSettingError(MeasurementError):
    """Raised if invalid settings keyword is passed to Measurement."""


class MissingSettingError(MeasurementError):
    """Raised if a settings keyword is missing."""


class NotOnGridError(MeasurementError):
    """Raised if specified scanning grid is not in accord with motor step size."""


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
    settings : dict with keys 'sampling_time', 'data_points', 'extent', 'mode'
        ``extent`` : tuple {((x0, x1, delta_x), (y0, y1, delta_y))
            hjkl
        ``sampling_time`` : float
            The desired sampling time in ms.
        ``data_points`` : int
            The number of data points to be acquired at each measuremet position.
        ``mode`` : str {'absolute', 'relative'}
            Sets the measuring area in relative or absolute coordinates.
    
    Example
    -------
      >>>
      >>>
      >>>
    """

    def __init__(self, host, serial_port, settings):
        self.controller = controller.Controller(host)
        self.table = table.Table(serial_port)
        self.position = None
        valid_keys = {'sampling_time', 'data_points', 'extent', 'mode'}
        missing_keys = valid_keys - settings.keys()
        invalid_keys = settings.keys() - valid_keys
        if invalid_keys:
            raise InvalidSettingError(str(invalid_keys))
        if missing_keys:
            raise MissingSettingError(str(missing_keys))
        self.settings = settings

    def __enter__(self):
        return self.initialize()

    def __exit__(self, *args):
        self.stop()

    def initialize(self):
        """
        Establishes all connections to the devices and performs some start up
        checks and a homing cycle if the current position is not known to grbl.
        """
        # TODO make sure __exit__ gets called if exception is raised here
        # http://stackoverflow.com/questions/13074847/catching-exception-in-context-manager-enter
        self.controller.connect()
        self.controller.check_status()
        self.table.connect()
        self.check_table_resolution()
        status = self.table.get_status()[0]
        if status.lower() == 'alarm':
            print("Homing ...")
            self.table.home()
        return self

    def stop(self):
        """Disconencts from all devices."""
        self.table.disconnect()
        self.controller.disconnect()

    def interactive_mode(self):
        """Starts the table's interactive mode."""
        feed = min(self.table.max_feed)
        self.table.serial_connection.command("G1 G90 F{}".format(feed))
        return self.table.interact()

    def move_away(self):
        """
        Moves the table to the outermost position. The previous position is
        preserved as an attribute, to be able to move back where you started.
        This function is useful to place the sample on the table without the
        sensor getting in the way.
        """
        self.position = self.table.get_status()[1]
        max_distance = (md - 0.1 for md in self.table.max_travel)
        self.table.move(*max_distance, mode='absolute')
        return self.position

    def move_back(self):
        """Moves the table back to the position stored by `move_away()`."""
        if self.position is not None:
            self.table.move(*self.position, mode='absolute')
        else:
            print("No position to move back to.")

    def move_to_start(self):
        """Moves the table to the starting position of the measurement."""
        self.table.move(self.settings['extent'][0][0],
                        self.settings['extent'][1][0], mode='absolute')

    def scan(self):
        """
        Rasters the measuring area. Halts at every measuring position and
        acquires a certain amount of data points (setting ``data_points``). The
        mean of this data sample is used as the data value at this position.

        Returns
        -------
        x, y : 1D-array
            The vectors spanning the measuring area
        z : 2D-arrary
            The acquired data values at the respective coordinates
        """
        # TODO check if extent in accord with max travel, maybe via grbl
        # checker, "$C"?

        x, y = self.vectors()
        positions = list(itertools.product(x, y))
        length = len(positions)
        z = np.zeros(length)
        self.controller.set_sampling_time(self.settings['sampling_time'])
        self.controller.set_trigger_mode('continuous')
        t_start = timer()
        for i, position in enumerate(positions):
            print("{i: >{width:}} of {length:}  |  ".format(
                i=i + 1, width=len(str(length)), length=length), end='')
            self.table.move(*position, mode='absolute')
            with self.controller.acquisition():
                z[i] = self.controller.get_data(self.settings['data_points'],
                                                channels=[0]).mean()
            t_end = timer()
            t_remaining = (length - i) * (t_end - t_start) / (i + 1)
            print("remaining: {}".format(format_remaining(t_remaining)))
        z = np.transpose(z.reshape((len(x), len(y))))
        return x, y, z

    def vectors(self):
        """
        Generates arrays with all x and y values of the measuring area (setting
        ``extent``).

        Returns
        -------
        vecs : list of arrays
            A list of arrays with all the x and y values, respectively.
        """
        if self.settings['mode'] == 'relative':
            position = self.table.get_status()[1]
        else:
            position = (0, 0)
        vecs = []
        for range_, offset in zip(self.settings['extent'], position):
            start, stop, step = range_
            vec = np.arange(start, stop + 0.5 * step, step, dtype=np.float)
            vec += offset
            vecs.append(vec)
        return vecs

    def check_table_resolution(self):
        """
        Checks if the grid points of the specified measuring area (setting 
        ``extent``) lie on the stepper motor grid.

        Raises
        ------
        NotOnGridError :
            If specified scanning grid is not in accord with motor step size.
        """
        resolution = self.table.resolution
        for res, extent in zip(resolution, self.settings['extent']):
            for value in extent:
                if not round((res * value), 8).is_integer():
                    message = ("extent value: {} mm; ".format(value) +
                               "stepper resolution: {} per mm".format(res))
                    raise NotOnGridError(message)


def format_remaining(seconds):
    """
    Formats a timedelta object to only show the seconds without the decimal
    places.
    """
    delta = str(datetime.timedelta(seconds=seconds + 0.5))
    return delta[:-7]
