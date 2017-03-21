import time
import serial

"""
Interface to the Arduino.
"""
# TODO make non-context-manager interface
class TableError(Exception):
    pass

class SerialConnection:
    """
    Interface to the serial port of the Arduino running grbl.
    """
    def __init__(self, port, baudrate=115200, timeout=0.5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection = None

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
        response = self.serial_connection.readlines()
        response = [r.decode('ascii').strip("\r\n") for r in response]
        if "ok" in response[-1]:
            if len(response) == 2:
                return response[0]
            else:
                return response[0:-1]
        else:
            raise TableError(response)
            #return "CAUTION: {}".format(response)


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
        time.sleep(1)
        self.serial_connection.serial_connection.readlines()
        # TODO remove $X when limit switches work
        self.serial_connection.command("$X")
        self.serial_connection.command("G91")

    def disconnect(self):
        self.serial_connection.disconnect()

    def get_status(self):
        # TODO check new grbl v1.1 syntax
        # TODO: make sure idle command is transmitted ($setting)
        """ """
        response = self.serial_connection.command("?").strip("<>").split(",")
        return response[0]

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
        self.serial_connection.command(self.g_code[mode])
        self.serial_connection.command("X{} Y{}".format(x, y))
        while self.get_status() != "Idle":
            time.sleep(0.5)

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

