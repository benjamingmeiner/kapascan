import controller
import table
import time
import math

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
        if stepsize % res_x != 0 or stepsize % res_y != 0:
            print("WARNING: Measurement step size is not a multiple
                    of stepper motor step size!")
        data = np.zeros((steps_y, steps_x))
        self.table.move(x=x0 y=y0, mode='absolute')
        with self.controller.acquisition():
            for i in range(steps_y):
                for j in range(steps_x):
                    self.controller.trigger()
                    data[i, j] = self.controller.get_data(channels=[0])
                    if i % 2 == 0:
                        self.table.move(x=stepsize)
                        # TODO use return value of move function and store result as coordinate positions.
                    else:
                        self.table.move(x=-stepsize)
                if i != steps_y - 1:
                    self.table.move(y=stepsize)
        return data

m =  Measurement()
with m:
    data = m.measure(1, 0.0005, 0.1)
