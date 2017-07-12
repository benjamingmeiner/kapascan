"""
A module that stores all relevant sensor data in the constant SENSORS.

Composition of the nested dict:
-------------------------------
key: serial number of sensor
value: dict with
    'name': Name of the sensor
    'channel': channel (demodulator) the sensor is connected to
    'range': Measuring range in µm
    'diamter': diameter of the sensing electrode in mm
"""

SENSORS = {
    '2011': {'serial_nr': '2011', 'name': 'CS2', 'channel':0, 'range': 2000, 'diameter': 8.2},
    '2012': {'serial_nr': '2012', 'name': 'CS2', 'channel':0, 'range': 2000, 'diameter': 8.2},
    '1739': {'serial_nr': '1739', 'name': 'CS05', 'channel':0, 'range': 500, 'diameter': 2},
}
