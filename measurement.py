import controller
import table
import time

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

    def measure(self, x_range, y_range, stepsize):
        #res_x, res_y = self.table.get_resolution()[0:2]
        x_steps = int(x_range / stepsize)
        y_steps = int(y_range / stepsize)
        self.table.move(x=10, y=10, mode='absolute')
        with self.controller.acquisition():
            for i in range(y_steps+1):
                for j in range(x_steps):
                    self.controller.trigger()
                    data = self.controller.get_data(channels=[0])
                    print(data)
                    self.table.move(x=stepsize)
                stepsize *= -1
                self.table.move(y=stepsize)

m =  Measurement()
with m:
    m.measure(10, 0.0005, 0.1)
