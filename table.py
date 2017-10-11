"""
This module provides an easy to use interface for the movement of the table.
The control of the stepper motors is done by grbl, which is an Arduino firmware,
originally intended for CNC milling motion control. The grbl project is located
at https://github.com/gnea/grbl/ with a very good wiki at
https://github.com/gnea/grbl/wiki.

Class listing
-------------
TableError :
    A simple exception class used for all errors in this module.
GrblError :
    An exception class mapping the grbl error codes to the corresponding error
    messages.
GrblAlarm :
    An exception class mapping the grbl alarm codes to the corresponding error
    messages.
SerialConnection :
    An interface to the serial port of the Arduino running grbl.
Table :
    Main interface for the control of the table.

Notes
-----
The control of the table is performed via the class methods of `Table`. The
class `SerialConnection` provides the low-level access to the serial port of the Arduino. All end-user functionality of the interface is implemented in class
`Table`, though.

Example
-------
  >>> table = Table('COM3')
  >>> with table:
  >>>     table.home()  # starts the homing cycle
  >>>     table.move(x=3, y=4, mode='absolute', feed='max')

grbl Settings
-------------
There have been made some minor changes to the grbl firmware (compile-time)
configuration (see file config.h in grbl source code):
 - The homing cycle routine is adapted to match the setup (no Z-axis)
 - The coordinate system is configured such that, in the top view on the table,
   the origin is at the lower left corner, with x pointing to the right and y
   pointing upwards.
 - The soft-reset character has been changed from `Ctrl-X` to `r`.

This is a listing of the recommended grbl (runtime) settings. See
https://github.com/gnea/grbl/wiki/Grbl-v1.1-Interface for the complete
documentation of the grbl interface::

$0=100
$1=0
$2=0
$3=3
$4=0
$5=0
$6=0
$10=1
$11=0.010
$12=0.002
$13=0
$20=1
$21=1
$22=1
$23=3
$24=25.000
$25=150.000
$26=15
$27=1.000
$30=1000
$31=0
$32=0
$100=1600.000
$101=1600.000
$102=200.000
$110=350.000
$111=350.000
$112=0.000
$120=8.000
$121=8.000
$122=0.000
$130=47.000
$131=47.000
$132=0.000
"""
# TODO check for exceptions that can be raised
# TODO use latest grbl runtime settings

import os
import time
import csv
import re
import logging
from contextlib import contextmanager
import serial
from .helper import query_yes_no, query_options
from .base import IOBase, Device, on_connection
from .helper import BraceMessage as __


logger = logging.getLogger(__name__)


class TableError(Exception):
    """Simple exception class used for all errors in this module."""


class SerialConenctionError(TableError):
    """Raised on serial connection errors."""


class ResetError(TableError):
    """Raised if grbl soft reset is unsuccessful."""


class UnlockError(TableError):
    """Raised if grbl unlock is unsuccessful."""


class NotConnectedError(TableError):
    """Raised if Connection to grbl is unsuccessful."""


class NotOnGridError(TableError):
    """Raised if scanning grid is not in accord with motor step size."""


class GrblError(TableError):
    """Mapping from grbl error codes to the corresponding error messages."""

    def __init__(self, i):
        self.i = int(i)
        super().__init__("Error {}: {}".format(i, self.error_message[self.i]))

    error_dirname = os.path.join(os.path.dirname(__file__), 'error_codes')
    with open(os.path.join(error_dirname, 'errors.csv'), newline='') as file:
        reader = csv.reader(file)
        error_message = {int(row[0]): row[2] for row in reader}


class GrblAlarm(TableError):
    """Mapping from grbl alarm codes to the corresponding error messages."""

    def __init__(self, i):
        self.i = int(i)
        super().__init__("ALARM {}: {}".format(i, self.alarm_message[self.i]))

    error_dirname = os.path.join(os.path.dirname(__file__), 'error_codes')
    with open(os.path.join(error_dirname, 'alarms.csv'), newline='') as file:
        reader = csv.reader(file)
        alarm_message = {int(row[0]): row[2] for row in reader}


class SerialConnection(IOBase):
    """
    Interface to the serial port of the Arduino running grbl.

    Parameters
    ----------
    serial_port : string
        The serial port on the host, e.g. `COM3` on Windows or `/dev/ttyACM0`
        on Linux.
    baud_rate : int, optional
        The baud rate of the connection. As of grbl v1.1 this defaults to 115200.
    timeout : int, optional
        The time in seconds that is waited when receiving input via readline()
        or readlines() methods.
    """
    regex = {'ok': r"ok",
             'error': r"error:(\d+)",
             'welcome_message': r"Grbl (\d+\.\d+[a-z]) \['\$' for help]",
             'alarm': r"ALARM:(\d)",
             'setting': r"\$(\d+)=(.+)",
             'startup_lines': r"\$N(0|1)=(.*)",
             'message': r"\[([A-Z0-9]{2,3}:.+)\]",
             'startup_execution': r">(.*):(ok|error:\d+)",
             'status': r"<([A-Za-z0-9:]{3,5})\|(MPos|WPos):([0-9.,-]+)(|\|.*)>",
             'empty': r"^$",
            }
    for key, pattern in regex.items():
        regex[key] = re.compile(pattern)


    def __init__(self, serial_port, baud_rate=115200):
        super().__init__((serial_port, baud_rate))
        # TODO: pass all known serial parameters for unambiguousness
        self.connection = serial.Serial()
        self.connection.port = self.address[0]
        self.connection.baudrate = self.address[1]
        self.connection.dtr = None
        self.connection.timeout = self.timeout
        self.connection.timeout = self.timeout

    def _open(self):
        """
        Opens the serial connection. The serial port cannot be used by another
        application at the same time or strange things will happen.
        """
        if not self.threads:
            while True:
                try:
                    self.connection.open()
                    break
                except serial.SerialException as error:
                    logger.error(error)
                    print(error)
                    if not query_yes_no("Retry?"):
                        raise NotConnectedError
            self.connection.write(b"\n\n")
            time.sleep(self.timeout)
            self.connection.flushInput()
            logger.debug(__("Connected to {} at {} baud.", *self.address))

    def _close(self):
        self.connection.close()
        logger.debug(__("Disconnected from {}.", self.address[0]))

    def _send(self, cmd):
        for seq in "\r\n":
            cmd = cmd.replace(seq, "")
        if cmd not in ['?', 'r', '~', '!']:
            cmd += "\n"
        logger.debug(__("Sending: {!r}", cmd))
        try:
            self.connection.write(cmd.encode('ascii'))
        except serial.SerialTimeoutException:
            msg = __("Timeout: Could not write '{}' to serial device.", cmd)
            logger.error(msg)
            raise TableError(msg)

    def _receive(self):
        line = self.connection.readline().decode('ascii')
        if line:
            logger.debug(__("Received: {!r}", line))
            line = line.strip("\r\n")
            return line
        else:
            return None

    def get_answer(self, timeout=None):
        """
        Overridden base method for the immediate parsing of the incoming
        messages.

        Returns
        -------
        messages : list of tuples
            all consecutive messages (parsed) until the acknowledging 'ok' from
            grbl.

        Raises
        ------
        GrblError :
            if grbl reports an error
        GrblAlarm :
            if grbl reports an alarm.

        See Also
        --------
        _parse : The method that parsed the messages.
        """
        messages = []
        while True:
            line = self._get_item(timeout=timeout)
            key, value = self._parse(line)
            messages.append((key, value))
            logger.debug(__("Parsed message: {} | {}", key, value))
            if key == 'error':
                error = GrblError(value[0])
                logger.error(error)
                raise GrblError(value[0])
            if key == 'alarm':
                error = GrblAlarm(value[0])
                logger.critical(error)
                raise error
            if key in ['ok', 'status']:
                break
        return messages

    def _parse(self, line):
        """
        Parses the received line.

        Parameters
        ----------
        line : str
            The message to be parsed

        Returns
        -------
        message : 2-tuple
            The pared message. First element of the tuple specifies the type of
            the message and can be one of the following strings:
              'ok', 'error', 'welcome_message', 'alarm', 'setting',
              'startup_lines', 'message', 'startup_execution', 'status', 'empty'
            The second element of the tuple holds a (possibly empty) list of
            the according values to the message type.

        Raises
        ------
        ConnectionError :
            If the message received from grbl is not understood.
        """
        message = None
        for key, pattern in self.regex.items():
            match = pattern.match(line)
            if match:
                groups = match.groups()
                message = (key, groups)
                break
        if message is None:
            raise ConnectionError(
                "Unrecognized response from grbl: {}".format(line))
        return message


class Table(Device):
    """
    Main interface for the usage of the table.

    Parameters
    ----------
    serial_port : string
        The serial port on the host, e.g. `COM3` on Windows or `/dev/ttyACM0`
        on Linux.
    baud_rate : int, optional
        The baud rate of the connection. As of grbl v1.1 this defaults to 115200.

    Coordinate system
    -----------------
    The coordinate system is configured such that, in the top view on the table,
    the origin is at the lower left corner, with x pointing to the right and y
    pointing upwards.

    Example
    -------
      >>> table = Table('COM3')
      >>> with table:
      >>>     table.home()  # starts the homing cycle
      >>>     table.move(x=3, y=4, mode='absolute', feed='max')
    """
    g_code = {'relative': 'G91',
              'absolute': 'G90'}

    def __init__(self, serial_port, baud_rate=115200):
        super().__init__()
        self.serial_connection = SerialConnection(serial_port, baud_rate)
        self.settings = None

    def _connect(self):
        self.serial_connection.connect()
        while True:
            try:
                answer = self.get_status()[0]
                logger.debug("Communication with grbl is ok.")
                return answer
            except TimeoutError:
                print("Grbl doesn't answer. Possible reasons could be:")
                print("  -- grbl is in an alarm state.")
                print("  -- grbl is too busy. (homing cycle, maybe?)")
                print("  -- another connection to grbl is still open.")
                print("What do you want to do?\n")
                option = query_options(["Do a soft-reset.",
                                        "Retry.",
                                        "Abort."])
                if option == 1:
                    self.reset()
                elif option == 2:
                    pass
                elif option == 3:
                    logger.debug("Connection aborted by user.")
                    raise NotConnectedError

    def _disconnect(self):
        self.serial_connection.disconnect()

    @on_connection
    def reset(self):
        """Initiates a soft-reset."""
        time.sleep(self.serial_connection.timeout)
        self.serial_connection.command("r", get_response=False)
        self.serial_connection.disconnect()
        self.serial_connection.connect()

    @on_connection
    def unlock(self):
        """
        Unlocks grbl for movements.

        Raises
        ------
        UnlockError :
            If unlock is not successful.
        """
        key, value = self.serial_connection.command("$X")[0]
        if key == 'message' and value[0] == 'MSG:Caution: Unlocked':
            logger.info("Unlocked manually.")
        elif key == 'ok':
            pass
        else:
            logger.error("grbl unlock failed.", exc_info=True)
            raise UnlockError

    @on_connection
    def _get_settings(self):
        """Queries grbl for its settings values."""
        logger.debug("Getting grbl settings.")
        answer = self.serial_connection.command("$$")
        settings = {}
        for key, value in answer:
            if key == 'setting':
                settings[int(value[0])] = float(value[1])
        self.settings = settings

    def _get_property(self, *n):
        """
        Gets the grbl settings. If the settings are not stored as class
        attributes yet, they are querried from grbl freshly.

        Parameters
        ----------
        n : int or sequence of ints
            the grbl setting id(s) to be returned

        Returns
        -------
        setting value or list of setting values
        """
        if self.settings is None:
            self._get_settings()
        return [self.settings[i] for i in n]

    @property
    def resolution(self):
        """Returns (x_res, y_res), the resolution of each axis in steps/mm."""
        return self._get_property(100, 101)

    @property
    def max_travel(self):
        """
        Returns (x_max, y_max), the maximal travel distance of each axis in mm.
        """
        return self._get_property(130, 131)

    @property
    def max_feed(self):
        """
        Returns (feed_x_max, feed_y_max), the maximal feed of each axis in
        mm/min.
        """
        return self._get_property(110, 111)

    @property
    def position(self):
        """Returns a tuple with the current position. (x,y)"""
        return self.get_status()[1]

    @on_connection
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
        key, value = self.serial_connection.command("?")[0]
        if key == 'status':
            status = value[0]
            if value[1] == 'MPos':
                position = value[2].split(",")[0:2]
            else:
                msg = "No machine position present in status report. Configure grbl!"
                logging.error(msg)
                raise TableError(msg)
            position = tuple(float(p) for p in position)
        return status, position

    @on_connection
    def home(self):
        """
        Starts the homing cycle. Blocks until finished.
        """
        logger.info("Homing ...")
        self.serial_connection.command("$H", timeout=30)

    @on_connection
    def move(self, x=None, y=None, mode='absolute', feed='max'):
        """
        Moves the table linearly to the desired coordinates.
        Blocks until movement is finished.

        Parameters
        ----------
        x, y : float, optional
            The coordinates in mm to move to. If a coordinate is omitted, it is
            not moved.

        mode : str {'relative', 'absolute'}, optional
            Move in relative or absolute coordinates. Defaults to 'absolute'.

        feed : float, optional
            The feed rate in mm/min. Defaults to the maximally allowed feed
            rate.

        Returns
        -------
        position : tuple of floats
            The machine position after the movement.
        """
        previous_position = self.position
        mode = mode.lower()
        if mode not in self.g_code.keys():
            raise TableError("Invalid move mode.")
        command = "G1 {} ".format(self.g_code[mode])
        if x is not None:
            command += "X{} ".format(x)
        if y is not None:
            command += "Y{} ".format(y)
        if feed == 'max':
            feed = min(self.max_feed)
        command += "F{}".format(feed)
        self.serial_connection.command(command)
        while True:
            status, position = self.get_status()
            if status.lower() == "idle" or status.lower() == "check":
                break
            else:
                # TODO: Auto optimize polling frequency based on step length
                time.sleep(0.014)
        return previous_position

    @on_connection
    def arc_move(self, x, y, r, mode='absolute', feed='max'):
        """
        Moves the table on an arc to the desired coordinates.
        Blocks until movement is finished.

        Parameters
        ----------
        x, y : float
            The coordinates in mm to move to.

        r : float
            The radius of the arc in mm.

        mode : str {'relative', 'absolute'}, optional
            Move in relative or absolute coordinates. Defaults to 'absolute'.

        feed : float, optional
            The feed rate in mm/min. Defaults to the maximally allowed feed
            rate.

        Returns
        -------
        position : tuple of floats
            The machine position after the movement.
        """
        mode = mode.lower()
        if mode not in self.g_code.keys():
            raise TableError("Invalid move mode.")
        if feed == 'max':
            feed = min(self.max_feed)
        command = "G2 {} X{} Y{} R{} F{}".format(self.g_code[mode], x, y, r, feed)
        self.serial_connection.command(command)
        while True:
            status, position = self.get_status()
            if status.lower() == "idle":
                break
            else:
                # TODO: Auto optimize polling frequency based on step length
                time.sleep(0.014)
        return position

    @on_connection
    def interact(self):
        """
        Starts the interactive mode, where the user can directly communicate
        with grbl.
        """
        print()
        print("Interactive Mode:\n"
              "=================\n\n"
              "(q to quit, r to reset)")
        history = []
        while True:
            command = input("---> ")
            if command == 'q':
                return self.get_status()[1]
            if command == 'r':
                self.reset()
            if command.startswith('.'):
                if set(command) == {'.'}:
                    i = command.count('.')
                command = history[-i]
                print("---> " + command)
            history.append(command)
            try:
                response = self.serial_connection.command(command)
                for line in response:
                    print(line)
            except GrblError as error:
                print(error)
            except GrblAlarm as error:
                if error.i == '2':
                    print(error)
                    if query_yes_no("Unlock?"):
                        self.reset()
                        self.unlock()
                    else:
                        print("Staying in ALARM state ...")
                else:
                    raise

    @on_connection
    def check_resolution(self, extent):
        """
        Checks if the grid points of the measuring area lie on the stepper motor
        grid.

        Parameters
        ----------
        extent : tuple {((x0, x1, delta_x), (y0, y1, delta_y))
            The coordinates of the boundary points of the measuring area
            (x0, x1, y0, y1) and the step size of each axis (delta_x, delta_y)

        Raises
        ------
        NotOnGridError :
            If specified scanning grid is not in accord with motor step size.
        """
        resolution = self.resolution
        for res, ext in zip(resolution, extent):
            for value in ext:
                if not round((res * value), 8).is_integer():
                    msg = __("extent value: {} mm; "
                             "motor resolution: {} steps per mm", value, res)
                    logger.error(msg)
                    raise NotOnGridError(msg)

    @contextmanager
    @on_connection
    def check_gcode_mode(self):
        """
        A context manager that switches grbl to g-code-check-mode.

        In g-code-check-mode grbl parses all input and answers the
        correspondingly, but it does not move the motors.
        """
        self.serial_connection.command("$C")
        logger.debug("Enabled g-code-check-mode.")
        try:
            yield
        finally:
            self.reset()
            self.serial_connection.command("$X")
            logger.debug("Disabled g-code-check-mode.")
