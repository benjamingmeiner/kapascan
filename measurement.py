import controller
import table

import itertools
import numpy as np

class Measurement():
    def __init__(self):
        self.controller = controller.Controller()
        self.table = table.Table()
        self.position = None

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
    - move_out()
    -   place sample
    - move_back()
    - find_range()
    - measure_sample()
    - move_out()
    -   remove sample
    - measure_background()
    """

    def move_back(self):
        if self.position is not None:
            self.table.move(self.position[0], self.position[1], 'absolute')
        else:
            print("No position to move back to.")

    def move_out(self):
        self.position = self.table.get_status()[1]
        x_max, y_max = self.table.get_max_travel()[0:2]
        self.table.move(x_max - 0.1, y_max - 0.1, 'absolute')

    def find_range(self, s, f):
        stay = True
        while stay:
            chars = input("'h' 'j' 'k' 'l' to move; 'q' to quit: ")
            for c in chars:
                num = ""
                if c.isdigit():
                    num + = c
                elif c in "hjklq":
                    r = int(num) if num != "" else 1
                    for i in range(r):
                        if c == "h":
                            pos = table.jog(x=s, f=f)
                        elif c == "j":
                            pos = table.jog(y=-s, f=f)
                        elif c == "k":
                            pos = table.jog(y=s, f=f)
                        elif c == "l":
                            pos = table.jog(x=-s, f=f)
                        elif c == "q":
                            stay = False
                            break
                else:
                    print("Not a valid input character: {}".format(c))
            print("X: {} | Y: {}".format(*pos))

    def measure_background(self):
        pass

    def measure_sample(self):
        pass

    def scan(self, x_start, y_start, x_stop, y_stop, stepsize):
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

