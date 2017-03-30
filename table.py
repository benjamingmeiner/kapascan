"""
This module provides an easy to use interface to grbl that allows basic table movements, as needed for measurements.

Class listing
-------------
SerialConnection :
    An interface to the serial port of the Arduino.
Table :
    Main interface for the control of the table.

Notes
-----
The control of the table is performed via the class methods of ``Table``. The class ``SerialConnection`` provides the low-level access to the serial port of the Arduino. All end-user functionality of the interface is implemented in class
``Table``, though.
"""
import time
import serial


# TODO push message checking, alarm usw...

class TableError(Exception):
    """Simple exception class used for all errors in this module."""
    pass

class SerialConnection:
    """
    Interface to the serial port of the Arduino UNO running grbl.

    An overview of all command that are understood by grbl can be found in the
    grbl wiki at:
    https://github.com/gnea/grbl/wiki

    Parameters
    ----------
    port : string
        The serial port on the host, e.g. 'COM3'.
    baudrate : int, optional
        The baudrate of the connection. As of grbl v1.1 this defaults to 115200
    timeout : int, optional
        The time in seconds that is waited when receiving input via readline() or
        readlines() methods.
    """
    def __init__(self, port, baudrate=115200, timeout=1):
        self.serial_connection = serial.Serial()
        self.serial_connection.port = port
        self.serial_connection.baudrate = baudrate
        self.serial_connection.timeout = timeout
        self.serial_connection.dtr = None

    def connect(self):
        """Open the serial connection. (Connection cannot be used by another application at the same time)"""
        # TODO catch exceptions here
        # TODO check response from first readlines. (alarm?, welcome message, nothing?)
        # TODO check what can be read if device in alarm mode
        self.serial_connection.open()
        self.serial_connection.write(b"\n\n")
        time.sleep(0.5)
        self.serial_connection.readlines()
        print("Connected to serial port")

    def disconnect(self):
        """Close the serial connection."""
        self.serial_connection.close()
        print("Disconnected from serial port")

    def command(self, com):
        """
        Send a command over the serial connection and return the response of the device.

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
        # TODO handle errors (and alarms?)
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
    
    Example
    -------
      >>>
      >>>
      >>>
    """
    g_code = {'relative': 'G91',
              'absolute': 'G90'}

    def __init__(self, serial_port='COM3', baudrate=115200):
        self.serial_connection = SerialConnection(serial_port, baudrate)

    def connect(self):
        """Connect to the serial port of the Arduino."""
        self.serial_connection.connect()

    def disconnect(self):
        """Disconnect from the serial port."""
        self.serial_connection.disconnect()

    def get_status(self):
        """ 
        Get the status of the device.
        
        Returns
        -------
        status : string
            The current state of the machine.
            Possible values: Idle, Run, Hold, Jog, Alarm, Door, Check, Home, Sleep

        position : tuple of floats
            The current machine position.
        """
        response = self.serial_connection.command("?")[0].strip("<>").split("|")
        status = response[0]
        # TODO check for existence of prefix of position (MPos) see https://github.com/gnea/grbl/wiki/Grbl-v1.1-Interface (end of file)
        position = response[1][5:].split(",")
        position = tuple(float(p) for p in position)
        return status, position

    def home(self):
        """Start the homing cycle."""
        self.serial_connection.command("$H")

    def move(self, x=0, y=0, mode):
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
        # TODO add G1 and feed rate
        self.serial_connection.command("{} X{} Y{}".format(self.g_code[mode], x, y))
        while True:
            status, position = self.get_status()
            if status.lower() == "idle":
                break
            #else:
            #    time.sleep(0.1)
        return position

    def jog(self, x=0, y=0, f=100, mode='relative'):
        """ Move the table in jogging mode.
        Jogging mode doesn't alter the g-code parser state. So parameters like
        feed rate or movement mode don't have to be reset after jogging.

        Parameters
        ----------
        x, y : float
            The coordinates to move to

        f : float
            The feed rate in mm/min

        mode : string, optional
            Move in relative or absolute coordinates with ``relative`` or
            ``absolute``
        """
        self.serial_connection.command("$J={} X{} Y{} F{}".format(
            self.g_code[mode], x, y, f))

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

    def get_max_travel(self):
        """Get the maximal travel distance of each axis in mm."""
        response = self.serial_connection.command("$$")
        for r in response:
            if r.startswith("$130"):
                var, x_max = r.split("=")
            if r.startswith("$131"):
                var, y_max = r.split("=")
            if r.startswith("$132"):
                var, z_max = r.split("=")
        return float(x_max), float(y_max), float(z_max)



