import controller
import table

class Measurement():
    def __init__(self):
        self.controller = controller.Controller()
        self.table = table.Table()

    def __enter__(self):
        self.controller.connect()
        self.table.connect()
        self.controller.check_status()
        pass

    def __exit__(self, *args):
        self.table.disconnect()
        self.controller.disconnect()

    def measure(self, x, y):
        res_x, res_y = self.table.get_resolution()[0:2]
        step_x = 1. / res_x
        step_y = 1. / res_y
        x_steps = x * res_x
        y_steps = y * res_y
        with self.controller.acquisition:
            for i in range(y_steps):
                for j in range(x_steps):
                    self.controller.trigger()
                    data = self.controller.get_data()
                    self.table.move(x=step_x)
                step_x *= -1
                self.table.move(y=step_y)


with Measurement() as m:
    m.measure(0.5, 0.5)
