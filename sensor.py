class Sensor:
    sensors = {'1234': {'range': 2000, 'diameter': 2},
               '5678': {'range': 3000, 'diameter' : 1},}

    def __init__(self, model):
        self.model = model
        for key, value in Sensor().sensors[model]:
            setattr(self, key, value)
