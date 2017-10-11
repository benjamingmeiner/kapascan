# kapascan
kapascan is a python framework I have written during my work on a scanning capacitance measurement setup for my masters thesis.
If you happen to use one of the devices from my setup and want to interface it with python, some modules could be useful to you.
Currently the setup comprises
* an capaNCDT DT6200 controller from Micro-Epsilon ([controller.py](controller.py))
* an Arduino Uno running grbl ([table.py](table.py))
* a data logger from Agilent ([data_logger.py](data_logger.py))
