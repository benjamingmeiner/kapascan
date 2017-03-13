import controller
import table

class Measurement():
    def __init__(self):
        self.controller = controller.Controller()
        self.table = table.Table()

    def measure(self):
        with self.controller as controller, self.table as table:
            controller.set_sampling_time(0)
            table.move(y=-2)
            print(controller.acquire(1))
            table.move(y=+2)
            print(controller.acquire(1))

m = Measurement()
m.measure()
