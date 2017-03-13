import controller
import table

class Measurement():
    def __init__(self):
        self.controller = controller.Controller()
        self.table = table.Table()

    def measure(self):
        with self.controller as controller, self.table as table:
            table.move(x=-0.5)
            table.move(x=+0.5)
            controller.set_sampling_time(1)
            print(controller.acquire(10))


m = Measurement()
m.measure()
