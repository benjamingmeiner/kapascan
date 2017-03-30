import controller
import table

import itertools
import numpy as np

class Measurement():
    def __init__(self, host='192.168.254.173', serial_port='COM3'):
        self.controller = controller.Controller(host)
        self.table = table.Table(serial_port)

        self.position = None
        self.area = [None, None]
        self.stepsize = None
        self.sampling_time = None
        self.background_data = None
        self.sample_data = None

    def __enter__(self):
        self.controller.connect()
        self.controller.check_status()
        self.table.connect()
        status, position = self.table.get_status()
        if status.lower() == 'alarm':
            self.table.home()
        return self

    def __exit__(self, *args):
        self.table.disconnect()
        self.controller.disconnect()

    """
    Procedure:
    ----------
    - move_away()
    -   place sample
    - move_back()
    - mark_out()
    - measure_sample()
    - move_away()
    -   remove sample
    - measure_background()
    """

    def move_back(self):
        """Move table to the stored position."""
        if self.position is not None:
            self.table.move(self.position[0], self.position[1], 'absolute')
        else:
            print("No position to move back to.")

    def move_away(self):
        """
        Move table to the outermost position while preserving the previous
        position as an attribute.
        """
        self.position = self.table.get_status()[1]
        x_max, y_max = self.table.get_max_travel()
        self.table.move(x_max - 0.1, y_max - 0.1, 'absolute')

    def mark_out(self, s, f):
        """
        Mark out the measuring area by manually moving the table to its edge
        points.
        """
        print("Move to lower edge of measuring area!")
        self.area[0] = self.table.cruize(0.1, 100)
        print("Move to upper edge of measurement area!")
        self.area[1] = self.table.cruize(0,1, 100)

    def measure_background(self):
        """Acquire data from background. Data is stored as attributes."""
        self.coordinates, self.background_data = self.scan()    

    def measure_sample(self):
        """Acquire data from sample. Data is stored as attributes."""
        self.coordinates, self.sample_data = self.scan()

    def scan(self):
        """
        Scans the defined area with the class' settings.
        """
        if not (self.sampling_time and self.area and self.data_points):
            break
        (x0, y0), (x1, y1) = self.area
        x_res, y_res = self.table.get_resolution()
        # TODO take care of numeric errors
        if (not (x_res * self.stepsize).is_integer() or
            not (y_res * self.stepsize).is_integer()):
            print("WARNING: Measurement step size is not a multiple of motor "
                  "step size! Stepper resolution is [steps/mm] "
                  "X: {}  Y: {}".format(x_res, y_res))
        x_range = np.arange(x0, x1, self.stepsize, dtype=np.float)
        y_range = np.arange(y0, y1, self.stepsize, dtype=np.float)
        positions = list(itertools.product(x_range, y_range))
        z = np.zeros(len(positions))
        for i, (xi, yi) in enumerate(positions):
            self.table.move(x=xi, y=yi, mode='absolute')
            with self.controller.acquisition(mode='continuous',
                                             sampling_time=self.sampling_time):
                data = self.controller.get_data(self.data_points, channels=[0])
                z[i] = data.mean()
        z = np.transpose(z.reshape((len(x_range), len(y_range))))
        return (x_range, y_range), z

    def get_data(self):
        return self.coordinates, self.sample_data[2] - self.background_data[2]
