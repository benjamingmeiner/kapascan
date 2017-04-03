"""
This module provides an easy to use interface for grbl that allows basic table
movements.

Class listing
-------------
SerialConnection :
    An interface to the serial port of the Arduino.
Table :
    Main interface for the control of the table.

Notes
-----
The control of the table is performed via the class methods of ``Table``. The
class ``SerialConnection`` provides the low-level access to the serial port of
the Arduino. All end-user functionality of the interface is implemented in class
``Table``, though.
"""

import time
import serial
from helper import query_yes_no

# TODO push message checking, alarm usw...


class TableError(Exception):
    """Simple exception class used for all errors in this module."""
    pass


class SerialConnection:
    """
    Interface to the serial port of the Arduino UNO running grbl.

    An overview of all command that are understood by grbl can be found in the
    grbl wiki at https://github.com/gnea/grbl/wiki.

    Parameters
    ----------
    port : string
        The serial port on the host, e.g. 'COM3'.
    baudrate : int, optional
        The baudrate of the connection. As of grbl v1.1 this defaults to 115200
    timeout : int, optional
        The time in seconds that is waited when receiving input via readline()
        or readlines() methods.
    """

    def __init__(self, serial_port, baudrate=115200, timeout=1):
        self.serial_connection = serial.Serial()
        self.serial_connection.port = serial_port
        self.serial_connection.baudrate = baudrate
        self.serial_connection.timeout = timeout
        self.serial_connection.dtr = None

    def connect(self):
        """
        Open the serial connection.
        The serial port cannot be used by another application at the same time.
        """
        # TODO check response from first readlines. (alarm?, welcome message,
        #      nothing?)
        # TODO check what can be read if device in alarm mode (nothing!)
        while True:
            try:
                self.serial_connection.open()
                break
            except serial.SerialException as error:
                print(error)
                if not query_yes_no("Retry?"):
                    break
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
        Send a command over the serial connection and return the response of
        the device.

        Parameters
        ----------
        com : string
            The command to be sent without trailing newline or carriage return 
            character.

        Returns
        -------
        response : list
            list of each line responded from the device.
        """
        # TODO handle other response messages than "ok and error"
        # TODO handle errors (and alarms?)
        # TODO Make this stable!!!
        self.serial_connection.write(com.encode('ascii') + b"\n")
        response = []
        while True:
            res = self.serial_connection.readline()
            res = res.decode('ascii').strip("\r\n")
            if "ok" in res:
                break
            if "error" in res or "Alarm" in res:
                response.append(res)
                break
            else:
                response.append(res)
        return response


class Table:
    # TODO grbl
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
            The current state of the machine. Possible values: 
            Idle, Run, Hold, Jog, Alarm, Door, Check, Home, Sleep

        position : tuple of floats
            The current machine position.

        Raises
        ------
        TableError :
            if no machine position (MPos) is present in grbl status report.
        """
        response = self.serial_connection.command("?")[0].strip("<>").split("|")
        status = response[0]
        position = response[1]
        if position.lower().startswith("mpos"):
            position = position[5:].split(",")
        else:
            raise TableError("No machine position present in status report."
                             "Configure grbl!")
        position = tuple(float(p) for p in position)
        return status, position[0:2]

    def get_resolution(self):
        """Get the resolution of each axis in steps/mm."""
        response = self.serial_connection.command("$$")
        for r in response:
            if r.startswith("$100"):
                _, x_res = r.split("=")
            if r.startswith("$101"):
                _, y_res = r.split("=")
        return float(x_res), float(y_res)

    def get_max_travel(self):
        """Get the maximal travel distance of each axis in mm."""
        response = self.serial_connection.command("$$")
        for r in response:
            if r.startswith("$130"):
                _, x_max = r.split("=")
            if r.startswith("$131"):
                _, y_max = r.split("=")
        return float(x_max), float(y_max)

    def home(self):
        """Start the homing cycle."""
        self.serial_connection.command("$H")

    def move(self, x, y, mode):
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

        Returns
        -------
        position : tuple of floats
            the machine position after the movement
        """
        mode = mode.lower()
        if mode not in Table().g_code.keys():
            print("Unrecognized move mode!")
        # TODO add G1 and feed rate
        self.serial_connection.command("{} X{} Y{}".format(
            self.g_code[mode], x, y))
        while True:
            status, position = self.get_status()
            if status.lower() == "idle":
                break
            else:
                time.sleep(0.1)
        return position

    def jog(self, x=0, y=0, feed=100, mode='relative'):
        """
        Move the table in jogging mode.
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
            self.g_code[mode], x, y, feed))

    def align(self, step, feed):
        stay = True
        while stay:
            chars = input("'h' 'j' 'k' 'l' to move; "
                          "'+' '-' to change stepsize; "
                          "'q' to quit: ")
            num = ""
            for c in chars:
                if c.isdigit():
                    num += c
                elif c in "hjklq+-":
                    r = int(num) if num != "" else 1
                    num = ""
                    for _ in range(r):
                        if c == "h":
                            self.jog(x=step, feed=feed)
                        elif c == "j":
                            self.jog(y=-step, feed=feed)
                        elif c == "k":
                            self.jog(y=step, feed=feed)
                        elif c == "l":
                            self.jog(x=-step, feed=feed)
                        elif c == "+":
                            step *= 2
                            print("New step size: {} mm".format(step))
                        elif c == "-":
                            step *= 0.5
                            print("New step size: {} mm".format(step))
                        elif c == "q":
                            stay = False
                            break
                else:
                    print("Not a valid input character: {}".format(c))
            pos = self.get_status()[1]
            print("X: {} | Y: {}".format(*pos))
        return pos
