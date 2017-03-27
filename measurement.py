import controller
import table

import itertools
import numpy as np

class Measurement():
    def __init__(self):
        self.controller = controller.Controller()
        self.table = table.Table()
        self.went_home = False

    def __enter__(self):
        self.controller.connect()
        self.table.connect()
        self.controller.check_status()
        if not self.went_home:
            self.table.home()
            self.went_home = True
        return self

    def __exit__(self, *args):
        self.table.disconnect()
        self.controller.disconnect()

    def measure(self, x_start, y_start, x_stop, y_stop, stepsize):
        x_res, y_res = self.table.get_resolution()[0:2]
        if not (x_res * stepsize).is_integer() or not (y_res * stepsize).is_integer():
            print("WARNING: Measurement step size is not a multiple of motor step size!" +
                  "Stepper resolution is [steps/mm]  X: {}  Y: {}".format(x_res, y_res))
        x_range = np.arange(x_start, x_stop, stepsize, dtype=np.float)
        y_range = np.arange(y_start, y_stop, stepsize, dtype=np.float)
        positions = list(itertools.product(x_range, y_range))
        z = np.zeros(len(positions))
        for i, (xi, yi) in enumerate(positions):
            self.table.move(x=xi, y=yi, mode='absolute')
            with self.controller.acquisition(mode='continuous'):
                data = self.controller.get_data(200, channels=[0])
                z[i] = data.mean()
        return x_range, y_range, np.transpose(z.reshape((len(x_range), len(y_range))))
