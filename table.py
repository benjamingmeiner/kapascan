import time
import serial

class SerialConnection:
    """
    Interface to the serial port of the Arduino running grbl
    """
    def __init__(self, port, baudrate=115200, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def connect(self):
        """ """
        self.serial_connection = serial.Serial(self.port, self.baudrate)

    def disconnect(self):
        """ """
        self.serial_connection.close()

    def command(self, com):
        """ """
        self.serial_connection.write()
        response = self.serial_connection.readlines()
