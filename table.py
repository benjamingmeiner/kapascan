import time
import serial

class TableError(Exception):
    pass

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
        """Open the connection to the serial connection."""
        # TODO catch exceptions here
        self.serial_connection = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        self.serial_connection.readlines()
        print("Connected to serial port")

    def disconnect(self):
        """Close the connection to the serial connection."""
        self.serial_connection.close()
        print("Disconnected from serial port")

    def command(self, com):
        #TODO: proper return value
        """
        Send a command over the serial connection.

        Parameters
        ----------
        com : string
            The command to be sent without trailing newline or carriage return.

        Returns
        -------
        response : string
            sth.
        """
        self.serial_connection.write(com.encode('ascii') + b"\n")
        response = self.serial_connection.readline().decode('ascii').strip("\r\n")
        if "ok" in response:
            return response
        else:
            return "CAUTION: {}".format(response)


class Table:
    """
    Interface to the Arduino.

    """
    g_code = {'relative': 'G91',
              'absolute': 'G90'}

    def __init__(self, serial_port='COM7', baudrate=115200):
        self.serial_connection = SerialConnection(serial_port, baudrate)

    def __enter__(self):
        self.serial_connection.connect()
        # TODO remove $X when limit switches work
        self.serial_connection.command("$X")
        return self

    def __exit__(self, *args):
        self.serial_connection.disconnect()

    def move(self, x=0, y=0, mode='relative'):
        """
        Moves the table to the desired coordinates.

        Parameters
        ----------
        x, y : float
            coordinates to move to

        mode : string
            move in relative or absolute coordinates with ``relative`` or
            ``absolute``
        """
        mode = mode.lower()
        if mode not in Table().g_code.keys():
            print("Unrecognized move mode!")
        # TODO: check response from command
        self.serial_connection.command(self.g_code[mode])
        self.serial_connection.command("X{} Y{}".format(x, y))

