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
        self.serial_connection = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        print(self.serial_connection.readlines())
        print("Connected to serial port")

    def disconnect(self):
        """ """
        self.serial_connection.close()

    def command(self, com):
        """ """
        self.serial_connection.write(com.encode('ascii') + b"\n")
        response = self.serial_connection.readline().decode('ascii').strip("\r\n")
        if "ok" in response:
            return response
        else:
            return "CAUTION: {}".format(response)


class Table:
    def __init__(self, port='COM7', baudrate=115200):
        self.serial_connection = SerialConnection(port, baudrate)
        self.g_code = {'relative': 'G91',
                       'absolute': 'G90'}

    def __enter__(self):
        self.serial_connection.connect()
        # TODO remove $X when limit switches work
        self.serial_connection.command("$X")
        return self

    def __exit__(self, *args):
        self.serial_connection.disconnect()

    def move(self, x=0, y=0, mode='relative'):
        mode = mode.lower()
        if mode not in self.g_code.keys():
            print("Unrecognized move mode!")
        print(self.serial_connection.command(self.g_code[mode]))
        print(self.serial_connection.command("X{} Y{}".format(x, y)))
