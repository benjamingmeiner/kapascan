import time
import serial

"""
Interface to the Arduino.
"""

# TODO push message checking, alarm usw...

class TableError(Exception):
    pass

class SerialConnection:
    """
    Interface to the serial port of the Arduino UNO running grbl.
    """
    def __init__(self, port, baudrate=115200, timeout=1):
        self.serial_connection = serial.Serial()
        self.serial_connection.port = port
        self.serial_connection.baudrate = baudrate
        self.serial_connection.timeout = timeout
        self.serial_connection.dtr = None

    def connect(self):
        """Open the serial connection."""
        # TODO catch exceptions here
        self.serial_connection.open()
        self.serial_connection.write(b"\n\n")
        time.sleep(2)
        self.serial_connection.readlines()
        print("Connected to serial port")

    def disconnect(self):
        """Close the serial connection."""
        self.serial_connection.close()
        print("Disconnected from serial port")

    def command(self, com):
        """
        Send a command over the serial connection and returns the response of the device.

        Parameters
        ----------
        com : string
            The command to be sent without trailing newline or carriage return.

        Returns
        -------
        response : list
            list of each line responded from the device.
        """
        # TODO handle other response messages than "ok and error"
        self.serial_connection.write(com.encode('ascii') + b"\n")
        response = []
        while True:
            res = self.serial_connection.readline().decode('ascii').strip("\r\n")
            if "ok" in res or "error" in res:
                break
            else:
                response.append(res)
        return response

class Table:
    """
    Interface to the Arduino.
    """
    g_code = {'relative': 'G91',
              'absolute': 'G90'}

    def __init__(self, serial_port='COM3', baudrate=115200):
        self.serial_connection = SerialConnection(serial_port, baudrate)

    def connect(self):
        self.serial_connection.connect()

    def disconnect(self):
        self.serial_connection.disconnect()

    def get_status(self):
        """ """
        response = self.serial_connection.command("?")[0].strip("<>").split("|")
        return response[0]

    def home(self):
        self.serial_connection.command("$H")

    def move(self, x=0, y=0, mode='relative'):
        """
        Moves the table to the desired coordinates.
        Blocks until finished.

        Parameters
        ----------
        x, y : float
            The coordinates to move to

        mode : string
            Move in relative or absolute coordinates with ``relative`` or
            ``absolute``
        """
        mode = mode.lower()
        if mode not in Table().g_code.keys():
            print("Unrecognized move mode!")
        self.serial_connection.command("{} X{} Y{}".format(self.g_code[mode], x, y))
        while self.get_status().lower() != "idle":
            time.sleep(0.2)

    def get_resolution(self):
        """Get the resolution of each axis in steps/mm."""
        response = self.serial_connection.command("$$")
        for r in response:
            if r.startswith("$100"):
                var, x_res = r.split("=")
            if r.startswith("$101"):
                var, y_res = r.split("=")
            if r.startswith("$102"):
                var, z_res = r.split("=")
        return float(x_res), float(y_res), float(z_res)

