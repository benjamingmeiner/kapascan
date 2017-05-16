"""
This module provides an easy to use interface for the movement of the table.
The control of the stepper motors is done by grbl, which is an Arduino firmware,
originally intended for CNC milling motion control. The grbl project is located
at https://github.com/gnea/grbl/ with a very good wiki at
https://github.com/gnea/grbl/wiki.

Class listing
-------------
SerialConnection :
    An interface to the serial port of the Arduino running grbl.
Table :
    Main interface for the control of the table.

Notes
-----
The control of the table is performed via the class methods of ``Table``. The
class ``SerialConnection`` provides the low-level access to the serial port of
the Arduino. All end-user functionality of the interface is implemented in class
``Table``, though.

Example
-------
  >>> table = Table('COM3')
  >>> table.connect()
  >>> table.home()  # starts the homing cycle
  >>> table.move(x=3, y=4, mode='absolute', feed='max')
  >>> table.disconnect()

grbl Settings
-------------
There have been made some minor changes to the grbl (compile-time) configuration
(see file config.h in grbl source code):
 - The homing cycle routine is adapted to match the setup (no Z-axis)
 - The coordinate system is configured such that, in the top view on the table,
   the origin is at the lower left corner, with x pointing to the right and y
   pointing upwards.
 - The soft-reset character has been changed from ``Ctrl-X`` to ``r``.

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
# TODO push message checking usw ...
# TODO check for exceptions that can be raised

import time
import serial
from .helper import query_yes_no, query_options


class TableError(Exception):
    """Simple exception class used for all errors in this module."""


class ResetError(TableError):
    """Raised if grbl soft reset is unsuccessful."""


class UnlockError(TableError):
    """Raised if grbl unlock is unsuccessful."""


class NotConnectedError(TableError):
    """Raised if Connection to grbl is unsuccessful."""


class TimeOutError(TableError):
    """Raised if timeout occurs on grbl status query."""


class NotOnGridError(TableError):
    """Raised if specified scanning grid is not in accord with motor step size."""


class GrblError(TableError):
    """Mapping from grbl error codes to the corresponding error messages."""

    def __init__(self, i):
        super().__init__("Error {}: {}".format(i, self.error_message[i]))
        self.i = i

    error_message = {
        '1': "G-code words consist of a letter and a value. Letter was not found.",
        '2': "Numeric value format is not valid or missing an expected value.",
        '3': "Grbl '$' system command was not recognized or supported.",
        '4': "Negative value received for an expected positive value.",
        '5': "Homing cycle is not enabled via settings.",
        '6': "Minimum step pulse time must be greater than 3usec.",
        '7': "EEPROM read failed. Reset and restored to default values.",
        '8': "Grbl '$' command cannot be used unless Grbl is IDLE. Ensures smooth operation during a job.",
        '9': "G-code locked out during alarm or jog state.",
        '10': "Soft limits cannot be enabled without homing also enabled.",
        '11': "Max characters per line exceeded. Line was not processed and executed.",
        '12': "(Compile Option) Grbl '$' setting value exceeds the maximum step rate supported.",
        '13': "Safety door detected as opened and door state initiated.",
        '14': "(Grbl-Mega Only) Build info or startup line exceeded EEPROM line length limit.",
        '15': "Jog target exceeds machine travel. Command ignored.",
        '16': "Jog command with no '=' or contains prohibited g-code.",
        '20': "Unsupported or invalid g-code command found in block.",
        '21': "More than one g-code command from same modal group found in block.",
        '22': "Feed rate has not yet been set or is undefined.",
        '23': "G-code command in block requires an integer value.",
        '24': "Two G-code commands that both require the use of the XYZ axis words were detected in the block.",
        '25': "A G-code word was repeated in the block.",
        '26': "A G-code command implicitly or explicitly requires XYZ axis words in the block, but none were detected.",
        '27': "N line number value is not within the valid range of 1 - 9,999,999.",
        '28': "A G-code command was sent, but is missing some required P or L value words in the line.",
        '29': "Grbl supports six work coordinate systems G54-G59. G59.1, G59.2, and G59.3 are not supported.",
        '30': "The G53 G-code command requires either a G0 seek or G1 feed motion mode to be active. A different motion was active.",
        '31': "There are unused axis words in the block and G80 motion mode cancel is active.",
        '32': "A G2 or G3 arc was commanded but there are no XYZ axis words in the selected plane to trace the arc.",
        '33': "The motion command has an invalid target. G2, G3, and G38.2 generates this error, if the arc is impossible to generate or if the probe target is the current position.",
        '34': "A G2 or G3 arc, traced with the radius definition, had a mathematical error when computing the arc geometry. Try either breaking up the arc into semi-circles or quadrants, or redefine them with the arc offset definition.",
        '35': "A G2 or G3 arc, traced with the offset definition, is missing the IJK offset word in the selected plane to trace the arc.",
        '36': "There are unused, leftover G-code words that aren't used by any command in the block.",
        '37': "The G43.1 dynamic tool length offset command cannot apply an offset to an axis other than its configured axis. The Grbl default axis is the Z-axis."}


class GrblAlarm(TableError):
    """Mapping from grbl alarm codes to the corresponding error messages."""

    def __init__(self, i):
        super().__init__("ALARM {}: {}".format(i, self.alarm_message[i]))
        self.i = i

    alarm_message = {
        '1': "Hard limit triggered. Machine position is likely lost due to sudden and immediate halt. Re-homing is highly recommended.",
        '2': "G-code motion target exceeds machine travel. Machine position safely retained. Alarm may be unlocked.",
        '3': "Reset while in motion. Grbl cannot guarantee position. Lost steps are likely. Re-homing is highly recommended.",
        '4': "Probe fail. The probe is not in the expected initial state before starting probe cycle, where G38.2 and G38.3 is not triggered and G38.4 and G38.5 is triggered.",
        '5': "Probe fail. Probe did not contact the workpiece within the programmed travel for G38.2 and G38.4.",
        '6': "Homing fail. Reset during active homing cycle.",
        '7': "Homing fail. Safety door was opened during active homing cycle.",
        '8': "Homing fail. Cycle failed to clear limit switch when pulling off. Try increasing pull-off setting or check wiring.",
        '9': "Homing fail. Could not find limit switch within search distance. Defined as 1.5 * max_travel on search and 5 * pulloff on locate phases."}


class SerialConnection:
    """
    Interface to the serial port of the Arduino running grbl.

    Parameters
    ----------
    serial_port : string
        The serial port on the host, e.g. 'COM3'.
    baudrate : int, optional
        The baudrate of the connection. As of grbl v1.1 this defaults to 115200
    timeout : int, optional
        The time in seconds that is waited when receiving input via readline()
        or readlines() methods.

    Example
    -------
    serial_connection = SerialConnection('COM3')
    serial_connection.connect()
    response = serial_connection.command("?")
    serial_connection.disconnect()
    """

    def __init__(self, serial_port, baudrate=115200, timeout=1):
        self.serial_connection = serial.Serial()
        self.serial_connection.port = serial_port
        self.serial_connection.baudrate = baudrate
        self.serial_connection.timeout = timeout
        self.serial_connection.dtr = None

    def connect(self):
        """
        Opens the serial connection.
        The serial port cannot be used by another application at the same time.
        """
        while True:
            try:
                self.serial_connection.open()
                break
            except serial.SerialException as error:
                print(error)
                if not query_yes_no("Retry?"):
                    raise NotConnectedError
        self.serial_connection.write(b"\n\n")
        time.sleep(0.5)
        self.serial_connection.readlines()

    def disconnect(self):
        """Closes the serial connection."""
        self.serial_connection.close()

    def command(self, com, timeout=30):
        """
        Sends a command to grbl over the serial connection and returns the
        response. The acknowledgement message 'ok' sent by grbl after each
        command is not returned by this function.

        Parameters
        ----------
        com : string
            The command to be sent without trailing newline or carriage return
            character.

        Returns
        -------
        response : list
            list of each line responded from the device.

        Raises
        ------
        GrblError, GrblAlarm :
            If grbl returns an error or an alarm.
        """
        self.serial_connection.write(com.encode('ascii') + b"\n")
        response = []
        start = time.time()
        while True:
            res = self.serial_connection.readline()
            res = res.decode('ascii').strip("\r\n")
            if "ok" in res:
                break
            if res != '':
                response.append(res)
            if "error:" in res:
                i = res.strip("error:")
                raise GrblError(i)
            if "ALARM:" in res:
                self.serial_connection.readlines()
                i = res.strip("ALARM:")
                raise GrblAlarm(i)
            if time.time() - start > timeout:
                raise TimeOutError(
                    "The device did not answer for {} seconds.".format(timeout))
        return response


class Table:
    """
    Main interface for the usage of the table.

    Coordinate system
    -----------------
    The coordinate system configured such that, in the top view on the table,
    the origin is at the lower left corner, with x pointing to the right and y
    pointing upwards.

    Example
    -------
      >>> table = Table('COM3')
      >>> table.connect()
      >>> table.home()  # starts the homing cycle
      >>> table.move(x=3, y=4, mode='absolute', feed='max')
      >>> table.disconnect()
    """
    g_code = {'relative': 'G91',
              'absolute': 'G90'}

    def __init__(self, serial_port, baudrate=115200):
        self.serial_connection = SerialConnection(serial_port, baudrate)
        self._max_travel = None
        self._max_feed = None
        self._resolution = None

    def connect(self):
        """Connects to the serial port of the Arduino running grbl."""
        self.serial_connection.connect()
        response = self.serial_connection.serial_connection.read_all()
        if response:
            print("Grbl messages present:")
            for line in response:
                print(line.decode('ascii'))
        while True:
            if self.is_alive() is True:
                self.serial_connection.serial_connection.read_all()
                return self.get_status()[0]
            else:
                print("Grbl doesn't answer. Possible reasons could be:")
                print("  -- grbl is in an alarm state.")
                print("  -- grbl is too busy. (homing cycle, maybe?)")
                print("What do you want to do?\n")
                option = query_options(["Do a soft-reset.",
                                        "Retry.",
                                        "Abort."])
                if option == 1:
                    self.reset()
                elif option == 2:
                    pass
                elif option == 3:
                    raise NotConnectedError

    def is_alive(self):
        self.serial_connection.serial_connection.read_all()
        try:
            self.serial_connection.command('', timeout=2)
        except TimeOutError as error:
            return False
        else:
            return True

    def disconnect(self):
        """Disconnects from the serial port."""
        self.serial_connection.disconnect()

    def reset(self):
        """
        Initiates a soft-reset.

        Raises
        ------
        ResetError :
            If reset is not successul.
        """
        self.serial_connection.serial_connection.write(b"r")
        response = self.serial_connection.serial_connection.readlines()
        if b"Grbl 1.1f ['$' for help]\r\n" in response:
            print("Reset.")
        else:
            raise ResetError

    def unlock(self):
        """
        Unlocks grbl for movements.

        Raises
        ------
        UnlockError :
            If unlock is not successful.
        """
        response = self.serial_connection.command("$X")
        if '[MSG:Caution: Unlocked]' in response:
            print("Unlocked.")
        else:
            raise UnlockError


    def _get_property(self, ids):
        response = self.serial_connection.command("$$")
        for line in response:
            if line.startswith("${}".format(ids[0])):
                _, x_prop = line.split("=")
            if line.startswith("${}".format(ids[1])):
                _, y_prop = line.split("=")
        return (float(x_prop), float(y_prop))


    @property
    def resolution(self):
        """
        Property resolution

        Returns
        -------
        x_res, y_res : float
            The resolution of each axis in steps/mm.
        """
        return self._get_property([100, 101])


    @property
    def max_travel(self):
        """
        Property max_travel

        Returns
        -------
        x_max, y_max : float
            The maximal travel distance of each axis in mm.
        """
        return self._get_property([130, 131])


    @property
    def max_feed(self):
        """
        Property max_feed

        Returns
        -------
        feed_x_max, feed_y_max : float
            The maximal feed of each axis in mm/min.
        """
        return self._get_property([110, 111])


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
        response = self.serial_connection.command("?")[0]
        response_fields = response.lower().strip("<>").split("|")
        status = response_fields[0]
        position = response_fields[1]
        if position.startswith("mpos:"):
            position = position[5:].split(",")[0:2]
        else:
            raise TableError("No machine position present in status report."
                             "Configure grbl!")
        position = tuple(float(p) for p in position)
        return status, position

    def home(self):
        """
        Starts the homing cycle. Blocks until finished.
        """
        self.serial_connection.command("$H")

    def move(self, x, y, mode, feed='max'):
        """
        Moves the table to the desired coordinates.
        Blocks until movement is finished.

        Parameters
        ----------
        x, y : float
            The coordinates to move to

        feed : float
            The feed rate in mm/min

        mode : str {'relative', 'absolute'}
            Move in relative or absolute coordinates.

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
        self.serial_connection.command("G1 {} X{} Y{} F{}".format(
            self.g_code[mode], x, y, feed))
        while True:
            status, position = self.get_status()
            if status.lower() == "idle":
                break
            else:
                time.sleep(0.05)
        return position

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
                    message = ("extent value: {} mm; ".format(value) +
                               "motor resolution: {} steps per mm".format(res))
                    raise NotOnGridError(message)

    def jog(self, x=0, y=0, feed=100, mode='relative'):
        """
        Move the table in jogging mode. Jogging mode doesn't alter the g-code
        parser state. So parameters like feed rate or movement mode don't have
        to be reset after jogging. Does *not* block until the movement is
        finished.

        Parameters
        ----------
        x, y : float
            The coordinates to move to

        feed : float
            The feed rate in mm/min

        mode : string, optional
            Move in relative or absolute coordinates with ``relative`` or
            ``absolute``
        """
        self.serial_connection.command("$J={} X{} Y{} F{}".format(
            self.g_code[mode], x, y, feed))
