import controller
import table
import time

import math
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

    def measure(self, x_range, y_range, stepsize, x0=0, y0=0):
        res_x, res_y = self.table.get_resolution()[0:2]
        steps_x = math.ceil(x_range / stepsize)
        steps_y = math.ceil(y_range / stepsize)
        x = np.zeros(steps_x * steps_y)
        y = np.zeros(steps_x * steps_y)
        z = np.zeros(steps_x * steps_y)
        n = 0
        x[n], y[n] = self.table.move(x=x0, y=y0, mode='absolute')[0:2]
        with self.controller.acquisition():
            for i in range(steps_y):
                for j in range(steps_x):
                    self.controller.trigger()                       
                    if i % 2 == 0:
                        step = stepsize
                    else:
                        step = -stepsize
                    z[n] = self.controller.get_data(channels=[0])
                    if j != steps_x - 1:
                        x[n+1], y[n+1] = self.table.move(x=step)[0:2]
                        n += 1
                if i != steps_y - 1:
                    x[n+1], y[n+1] = self.table.move(y=stepsize)[0:2]
                    n += 1
        return x, y, z

m =  Measurement()
with m:
    x, y, z = m.measure(2, 2, 0.7)
