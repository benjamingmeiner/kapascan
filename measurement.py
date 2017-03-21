import controller
import table
import time

class Measurement():
    def __init__(self):
        self.controller = controller.Controller()
        self.table = table.Table()

    def __enter__(self):
        self.controller.connect()
        self.table.connect()
        self.controller.check_status()
        return self

    def __exit__(self, *args):
        self.table.disconnect()
        self.controller.disconnect()

    def measure(self, x, y):
        res_x, res_y = self.table.get_resolution()[0:2]
        step_x = 100. / res_x
        step_y = 100. / res_y
        print(step_x)
        print(step_y)
        x_steps = int(x * res_x / 100)
        y_steps = int(y * res_y / 100)
        with self.controller.acquisition():
            for i in range(y_steps):
                for j in range(x_steps):
                    print(j)
                    #self.controller.trigger()
                    #data = self.controller.get_data()
                    #print(data)
                    #time.sleep(0.1)
                    self.table.move(x=step_x)
                step_x *= -1
                self.table.move(y=step_y)


with Measurement() as m:
    m.measure(2, 2)
