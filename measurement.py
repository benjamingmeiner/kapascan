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
    def __init__(self, host, serial_port, x_range=None, y_range=None,
                 sampling_time=None, data_points=None):
        self.controller = controller.Controller(host)
        self.table = table.Table(serial_port)
        self.position = None
        self.settings = dict(x_range=x_range, y_range=y_range,
                             sampling_time=sampling_time,
                             data_points=data_points)
        self.data = dict(coordinates=None, background=None, sample=None)

    def __enter__(self):
        return self.initialize()

    def __exit__(self, *args):
        self.stop()

    def initialize(self):
        self.controller.connect()
        self.controller.check_status()
        self.table.connect()
        status = self.table.get_status()[0]
        if status.lower() == 'alarm':
            self.table.home()
        return self

    def stop(self):
        self.table.disconnect()
        self.controller.disconnect()

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
        if self.settings['xy_range'] is not None:
            self.table.move(self.settings['x_range'][0],
                            self.settings['y_range'][0], mode='absolute')
        else:
            print("No measurement area set yet.")

    def scan(self):
        """
        Rasters the measuring area. Halts at every measuring position and
        acquires a certain amount of data points. The mean of this data sample
        is used as the data value at this position.

        Returns
        -------
        x, y : 1D-array
            The vectors spanning the measuring area
        z : 2D-arrary
            The acquired data values at the respective coordinates
        """
        self.check_settings()
        x = vector(*self.settings['x_range'])
        y = vector(*self.settings['y_range'])
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

    def check_settings(self):
        for value in self.settings.values():
            if not value:
                raise MeasurementError("Not all parameters have been set yet.")
        x_res, y_res = self.table.resolution
        # TODO take care of numeric errors
        if (not (x_res * self.settings['x_range'][2]).is_integer() or
                not (y_res * self.settings['y_range'][2]).is_integer()):
            raise MeasurementError("Measurement step size is not a multiple of "
                "motor step size! Stepper resolution is [steps/mm] "
                "X: {}  Y: {}".format(x_res, y_res))


def vector(start, stop, step, dtype=np.float):
    return np.arange(start, stop + 0.5 * step, step, dtype=dtype)

def format_remaining(seconds):
    delta = str(datetime.timedelta(seconds=seconds+0.5))
    return delta[:-7]


#    def measure(self):
#        """ Starts a guided measurement cycle. """
#        self.move_away()
#        print("Place sample!")
#        if not query_yes_no("Continue?"):
#            print("Abort.")
#            return
#
#        self.move_back()
#        if self.settings['xy_range'] is None:
#            self.set_area()
#        else:
#            print("Measuring area already set.")
#            if query_yes_no("Mark out area again?"):
#                self.set_area()
#        print("Done.")
#
#        for value in self.settings.values():
#            if value is None:
#                print("Error: Not all parameters have been set yet.")
#                print("Abort.")
#                return
#
#        print("Current settings:")
#        print(self.settings)
#        if not query_yes_no("Start measurement?"):
#            print("Abort.")
#            return
#        self.data['coordinates'], self.data['sample'] = self.scan(**self.settings)
#        print("Done.")
#
#        self.move_away()
#        input("Remove sample! Press <Enter> to continue.")
#
#        self.move_to_start()
#        if not query_yes_no("Start measurement of background?"):
#            print("Abort.")
#            return self
#        self.data['coordinates'], self.data['background'] = self.scan(
#            **self.settings)
#        print("Done.")
#
#        return self
