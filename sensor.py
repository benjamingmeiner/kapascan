"""
A module that stores all relevant sensor data in the constant SENSORS.

Composition of the nested dict:
-------------------------------
key: serial number of sensor
value: dict with
    'name': Name of the sensor
    'channel': channel (demodulator) the sensor is connected to
    'range': Measuring range in µm
    'diameter': diameter of the sensing electrode in mm
"""

# TODO update diameters and add edge width

SENSORS = {
    '2011': {'serial_nr': '2011', 'name': 'CS2', 'channel':0, 'range': 2000, 'diameter': 7.9},
    '2012': {'serial_nr': '2012', 'name': 'CS2', 'channel':1, 'range': 4000, 'diameter': 7.9},
    '1739': {'serial_nr': '1739', 'name': 'CS05', 'channel':1, 'range': 1000, 'diameter': 3.9},
    '1161': {'serial_nr': '1161', 'name': 'CS02', 'channel':1, 'range': 400, 'diameter': 2.3},
}
