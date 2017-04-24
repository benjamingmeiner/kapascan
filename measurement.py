"""
YO
"""
import controller
import table
#from helper import query_yes_no

import itertools
import numpy as np
from timeit import default_timer as timer
import datetime

class MeasurementError(Exception):
    pass

class InvalidSettingError(MeasurementError):
    pass

class MissingSettingError(MeasurementError):
    pass

class NotOnGridError(MeasurementError):
    pass

class Measurement():
    """
    Parameters
    ----------
    host : str
        The IP address of the controller.
    serial_port : str
        The serial port of the Arduino running grbl.
    xy_range : tuple {((x0, x1), (y0, y1))}
        x0, x1: x range of the measuring area.
        y0, y1: x range of the measuring area.
    step_size : float
        The step size between two measuring points.
    sampling_time : float
        The desired sampling time in ms.
    data_points : int
        The number of data points to be acquired at each measurement
        position.
    """
    def __init__(self, host, serial_port, settings):
        self.controller = controller.Controller(host)
        self.table = table.Table(serial_port)
        self.position = None
        valid_keys = {'sampling_time', 'data_points', 'extent'}
        missing_keys = valid_keys - settings.keys()
        invalid_keys =  settings.keys() - valid_keys
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
        # TODO make sure __exit__ gets called if exception is raised here
        # http://stackoverflow.com/questions/13074847/catching-exception-in-context-manager-enter
        self.controller.connect()
        self.controller.check_status()
        self.table.connect()
        self.check_resolution()
        status = self.table.get_status()[0]
        if status.lower() == 'alarm':
            print("Homing ...")
            self.table.home()
        return self

    def stop(self):
        self.table.disconnect()
        self.controller.disconnect()

    def interactive_mode(self):
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

    def scan(self, mode='absolute'):
        """
        Rasters the measuring area. Halts at every measuring position and
        acquires a certain amount of data points. The mean of this data sample
        is used as the data value at this position.

        Parameters
        ----------
        mode : str {'absolute', 'relative'}

        Returns
        -------
        x, y : 1D-array
            The vectors spanning the measuring area
        z : 2D-arrary
            The acquired data values at the respective coordinates
        """
        if mode not in ('relative', 'absolute'):
            raise MeasurementError("Invalid argument mode={}".format(mode))
        # TODO check if extent in accord with max travel, maybe via grbl checker, "$C"?


        x, y = self.vectors(mode)
        positions = list(itertools.product(x, y))
        length = len(positions)
        z = np.zeros(length)
        self.controller.set_sampling_time(self.settings['sampling_time'])
        self.controller.set_trigger_mode('continuous')
        t_start = timer()
        for i, position in enumerate(positions):
            print("{i: >{width:}} of {length:}  |  ".format(
                i=i+1, width=len(str(length)), length=length), end='')
            self.table.move(*position, mode='absolute')
            with self.controller.acquisition():
                z[i] = self.controller.get_data(self.settings['data_points'],
                                                channels=[0]).mean()
            t_end = timer()
            t_remaining = (length - i) * (t_end - t_start) / (i + 1)
            print("remaining: {}".format(format_remaining(t_remaining)))
        z = np.transpose(z.reshape((len(x), len(y))))
        return x, y, z

    def vectors(self, mode):
        if mode == 'relative':
            position = self.table.get_status()[1]
        else:
            position = (0, 0)
        vectors = []
        for range_, offset in zip(self.settings['extent'], position):
            start, stop, step = range_
            vector = np.arange(start, stop + 0.5 * step, step, dtype=np.float)
            vector += offset
            vectors.append(vector)
        return vectors

    def check_resolution(self):
        resolution = self.table.resolution
        for res, extent in zip(resolution, self.settings['extent']):
            for value in extent:
                if not round((res * value), 8).is_integer():
                    raise NotOnGridError("extent value: {} mm; ".format(value) +
                        "stepper resolution: {} per mm".format(res))


def format_remaining(seconds):
    delta = str(datetime.timedelta(seconds=seconds+0.5))
    return delta[:-7]
