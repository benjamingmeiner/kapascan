"""
YO
"""
import controller
import table

import itertools
import numpy as np


class MeasurementError(Exception):
    pass


class Measurement():
    def __init__(self, host='192.168.254.173', serial_port='COM3', area=None,
                 step_size=None, sampling_time=None, data_points=None):
        self.controller = controller.Controller(host)
        self.table = table.Table(serial_port)
        self.position = None
        self.settings = dict(step_size=step_size, sampling_time=sampling_time,
                             area=area, data_points=data_points)
        self.data = dict(coordinates=None, background=None, sample=None)

    def __enter__(self):
        self.controller.connect()
        self.controller.check_status()
        self.table.connect()
        status = self.table.get_status()[0]
        if status.lower() == 'alarm':
            self.table.home()
        return self

    def __exit__(self, *args):
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
        x_max, y_max = self.table.get_max_travel()
        self.table.move(x_max - 0.1, y_max - 0.1, 'absolute')
        return self.position

    def move_back(self):
        """Moves the table back to the position stored by `move_away()`."""
        if self.position is not None:
            self.table.move(self.position[0], self.position[1], 'absolute')
        else:
            print("No position to move back to.")

    def move_to_start(self):
        """Moves the table to the starting position of the measurement."""
        if self.settings.area is not None:
            self.table.move(*self.settings.area[0], mode='absolute')
        else:
            print("No measurement area set yet.")

    def move_to_center(self):
        """ Moves to the center (approximately) of the table.""" 
        self.position = self.table.get_status()[1]
        x_max, y_max = self.table.get_max_travel()
        self.table.move(x_max * 0.5, y_max * 0.5, 'absolute')
        return self.position

    def set_area(self, step=0.2, feed=100):
        """
        Mark out the measuring area by manually moving the table to its edge
        points.
        """
        print("Move to lower edge of measuring area!")
        pos0 = self.table.align(step, feed)
        print("Move to upper edge of measurement area!")
        pos1 = self.table.align(step, feed)
        self.settings['area'] = (pos0, pos1)
        print("Set area.")
        return self.settings['area']

    def scan(self, area, step_size, sampling_time, data_points):
        """
        Rasters the measuring area. Halts at every measuring position and
        acquires a certain amount of data points. The mean of this data sample
        is used as the data value at this position.

        Notes
        -----
        All parameters default to their corresponding class attributes.
        This way you can easily repeat measurements with identical settings.

        Parameters
        ----------
        area : tuple {((x0, y0), (x1, y1))}
            x0, y0: coordinates of lower edge of measuring area
            x1, y1: coordinates of upper edge of measuring area

        step_size : float
            The step size between two measuring points.

        sampling_time : float
            The desired sampling time in ms.

        data_points : int
            The number of data points to be acquired at each measurement
            position.
        """
        if not (sampling_time and area and data_points and step_size):
            raise MeasurementError("Not all parameters have been set yet.")
        x_res, y_res = self.table.get_resolution()
        # TODO take care of numeric errors
        if (not (x_res * step_size).is_integer() or
                not (y_res * step_size).is_integer()):
            print("WARNING: Measurement step size is not a multiple of motor "
                  "step size! Stepper resolution is [steps/mm] "
                  "X: {}  Y: {}".format(x_res, y_res))
        x_range, y_range = zip(*area)
        x = np.arange(x_range[0], x_range[1], step_size, dtype=np.float)
        y = np.arange(y_range[0], y_range[1], step_size, dtype=np.float)
        positions = list(itertools.product(x, y))
        z = np.zeros(len(positions))
        for i, position in enumerate(positions):
            self.table.move(*position, mode='absolute')
            with self.controller.acquisition('continuous', sampling_time):
                z[i] = self.controller.get_data(data_points, channels=[0]).mean()
        z = np.transpose(z.reshape((len(x), len(y))))
        return np.array((x, y)), z

    def measure(self):
        """
        Starts a guided measurement cycle.

        Returns
        -------
        coordinates : tuple of arrays {(x, y)}
            arrays with the vectors spanning the measuring area

        background_data : 2D array
            The acquired data without sample

        sample_data : 2D array
            The acquired data with the sample
        """
        self.move_away()
        print("Place sample!")
        if not query_yes_no("Continue?"):
            print("Abort.")
            return

        self.move_to_center()
        if self.settings['area'] is None:
            self.set_area()
        else:
            print("Measuring area already set.")
            if query_yes_no("Mark out area again?"):
                self.set_area()
        print("Done.")

        for value in self.settings.values():
            if value is None:
                print("Error: Not all parameters have been set yet.")
                print("Abort.")
                return

        print("Current settings:")
        print(self.settings)
        if not query_yes_no("Start measurement?"):
            print("Abort.")
            return
        self.data['coordinates'], self.data['sample'] = self.scan(**self.settings)
        print("Done.")

        self.move_away()
        input("Remove sample! Press <Enter> to continue.")

        self.move_to_start()
        if not query_yes_no("Start measurement of background?"):
            print("Abort.")
            return
        self.data['coordinates'], self.data['background'] = self.scan(
            **self.settings)
        print("Done.")

        return self.data


def query_yes_no(question, default="yes"):
    """
    Asks a yes/no question via input() and returns the answer.

    Parameters
    ----------
    question : str
        The string that is presented to the user.

    default : str {"yes", "no"}, optional
        The presumed answer if the user just hits <Enter>.

    Returns
    -------
    answer : bool
        True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)
    while True:
        print(question + prompt, end='')
        choice = input("--->  ").lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            print("Please respond with 'yes' or 'no' (or 'y' or 'n').")
