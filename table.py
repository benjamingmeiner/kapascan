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
# TODO check for exceptions that can be raised

import time
import csv
import threading
import queue
import re
from functools import wraps
import serial
from helper import query_yes_no, query_options, cached_property


class TableError(Exception):
    """Simple exception class used for all errors in this module."""


class ConenctionError(TableError):
    """Raised on serial connection errors."""


class ResetError(TableError):
    """Raised if grbl soft reset is unsuccessful."""


class UnlockError(TableError):
    """Raised if grbl unlock is unsuccessful."""


class NotConnectedError(TableError):
    """Raised if Connection to grbl is unsuccessful."""


class TimeOutError(TableError):
    """Raised if timeout occurs on grbl status query."""


class NotOnGridError(TableError):
    """Raised if scanning grid is not in accord with motor step size."""


class GrblError(TableError):
    """Mapping from grbl error codes to the corresponding error messages."""

    def __init__(self, i):
        super().__init__("Error {}: {}".format(i, self.error_message[i]))
        self.i = i

    with open('error_codes/error_codes_en_US.csv', newline='') as file:
        reader = csv.reader(file)
        error_message = {row[0]: row[2] for row in reader}


class GrblAlarm(TableError):
    """Mapping from grbl alarm codes to the corresponding error messages."""

    def __init__(self, i):
        super().__init__("ALARM {}: {}".format(i, self.alarm_message[i]))
        self.i = i

    with open('error_codes/alarm_codes_en_US.csv', newline='') as file:
        reader = csv.reader(file)
        alarm_message = {row[0]: row[2] for row in reader}


class SerialConnection:
    """
    Interface to the serial port of the Arduino running grbl.

    Parameters
    ----------
    serial_port : string
        The serial port on the host, e.g. 'COM3'.
    baud_rate : int, optional
        The baud rate of the connection. As of grbl v1.1 this defaults to 115200
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


    def __init__(self, serial_port, baud_rate=115200, timeout=2):
        # TODO: pass all known serial parameters
        self.serial_connection = serial.Serial()
        self.serial_connection.port = serial_port
        self.serial_connection.baudrate = baud_rate
        self.serial_connection.dtr = None
        self.timeout = timeout
        self.serial_connection.timeout = self.timeout
        self.io_threads = []
        self.out_queue = queue.Queue()
        self.in_queue = queue.Queue()
        self._stop_flag = False

    def connect(self):
        """
        Opens the serial connection and starts the I/O threads.
        The serial port cannot be used by another application at the same time.
        """
        if not self.io_threads:
            self._stop_flag = False
            while True:
                try:
                    self.serial_connection.open()
                    break
                except serial.SerialException as error:
                    print(error)
                    if not query_yes_no("Retry?"):
                        raise NotConnectedError
            self.serial_connection.write(b"\n\n")
            time.sleep(self.timeout)
            self.serial_connection.flushInput()
            targets = (self._input, self._output)
            for target in targets:
                thread = threading.Thread(target=target, args=(self._stop,))
                self.io_threads.append(thread)
                thread.start()

    def disconnect(self):
        """Closes the serial connection and stops the I/O threads."""
        self._stop_flag = True
        for thread in self.io_threads:
            thread.join()
        self.io_threads.clear()
        self.serial_connection.close()

    def command(self, cmd, timeout=None):
        """
        Sends a command to grbl and returns its response.

        The function returns all subsequent lines of the device including the
        acknowledging 'ok', which is the last line of the answer.

        Parameters
        ----------
        cmd : str
            The command to be sent.
        timeout: float, optional
            The maximal time in seconds that is waited for a response from the
            device. If timout is None, the timeout value of the class is used.

        Returns
        -------
        answer :
            The pre-parsed answer from the device. See docstring of
            '_method_parser' for the format of the parsed messages.

        Raises
        ------
        TimeOutError :
            If no more messages are present in the input queue, although the
            response of the device is not complete. (Missing 'ok')
        """
        if timeout is None:
            timeout = self.timeout
        self.out_queue.put(cmd)
        answer = []
        while True:
            try:
                message = self.in_queue.get(timeout=timeout)
            except queue.Empty:
                raise TimeOutError(
                    "No/incomplete response to command '{}'.".format(cmd) +
                    "I/O threads still alive?")
            answer.append(message)
            if message[0] == 'ok':
                break
        return answer

    def _stop(self):
        """
        This function is called from all threads that run eternally, to check
        when it is time to exit.
        """
        return self._stop_flag

    def _input(self, stop):
        """
        Target function of the input thread. Puts all received and parsed
        messages into the in_queue."""
        while not stop():
            line = self.serial_connection.readline()
            if line:
                line = line.decode('ascii').strip("\r\n")
                print("Got: {}".format(repr(line)))
                key, value = self._message_parser(line)
                print("Parsed: {} | {}".format(key, value))
                if key == 'error':
                    raise GrblError(value[0])
                if key == 'alarm':
                    raise GrblAlarm(value[0])
                if key == 'empty':
                    continue
                self.in_queue.put((key, value))

    def _output(self, stop):
        """
        Target function of the output thread. Takes commands from the out_queue
        and writes them to the serial connection.
        """
        while not stop():
            try:
                cmd = self.out_queue.get(timeout=self.timeout)
            except queue.Empty:
                continue
            for seq in "\r\n":
                cmd = cmd.replace(seq, "")
            cmd = cmd.encode('ascii') + b"\n"
            print("Sending: {}".format(cmd))
            self.serial_connection.write(cmd)

    def _message_parser(self, msg):
        """
        Parses the received messages.

        Parameters
        ----------
        msg : str
            The message to be parsed

        Returns
        -------
        message : 2-tuple
            The pared message. First element of the tuple specifies the type of
            the message and can be one of the following strings:
              'ok', 'error', 'welcome_message', 'alarm', 'setting',
              'startup_lines', 'message', 'startup_execution', 'status', 'empty'
            The second element of the tuple hold a (possibly empty) list of the
            according values to the message type.

        Raises
        ------
        ConnectionError :
            If the message received from grbl is not understood.
        """
        message = None
        for key, pattern in self.regex.items():
            match = pattern.match(msg)
            if match:
                groups = match.groups()
                message = (key, groups)
                break
        if message is None:
            raise ConnectionError("Unrecognized response from grbl: {}".format(msg))
        return message


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

    def __init__(self, serial_port, baud_rate=115200):
        self.serial_connection = SerialConnection(serial_port, baud_rate)
        self.connected = False

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.disconnect()

    def connect(self):
        """Connects to the serial port of the Arduino running grbl."""
        self.serial_connection.connect()
        self.connected = True
        while True:
            try:
                return self.get_status()[0]
            except TimeOutError:
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

    def disconnect(self):
        """Disconnects from the serial port."""
        self.serial_connection.disconnect()
        self.connected = False

    def _on_connection(f):
        """
        Decorator for methods that are only allowed to be called if the
        connection is established.

        Raises
        ------
        NotConnectedError :
            If the Table instance is not connected.
        """
        @wraps(f)
        def checked(self, *args, **kwargs):
            if self.connected:
                return f(self, *args, **kwargs)
            else:
                raise NotConnectedError
        return checked

    @_on_connection
    def reset(self):
        """
        Initiates a soft-reset.

        Raises
        ------
        ResetError :
            If reset is not successul.
        """
        key, _ = self.serial_connection.command("r")[0]
        if key == 'welcome_message':
            print("Reset.")
        else:
            raise ResetError

    @_on_connection
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
            print("Caution! Unlocked.")
        if key == 'ok':
            print("Unlocked already.")
        else:
            raise UnlockError

    @_on_connection
    def _get_property(self, ids):
        """
        Gets grbl '$'-settings.

        Parameters
        ----------
        ids : list of int
            list with the grbl setting IDs to be fetched.

        Returns
        -------
        properties : list of floats
            list with the corresponding setting values.
        """
        answer = self.serial_connection.command("$$")
        properties = []
        for id in ids:
            for key, value in answer:
                if key == 'setting' and value[0] == str(id):
                    properties.append(float(value[1]))
        return properties

    @cached_property
    @_on_connection
    def resolution(self):
        """Returns (x_res, y_res), the resolution of each axis in steps/mm."""
        return self._get_property([100, 101])

    @cached_property
    @_on_connection
    def max_travel(self):
        """
        Returns (x_max, y_max), the maximal travel distance of each axis in mm.
        """
        return self._get_property([130, 131])

    @cached_property
    @_on_connection
    def max_feed(self):
        """
        Returns (feed_x_max, feed_y_max), the maximal feed of each axis in
        mm/min.
        """
        return self._get_property([110, 111])

    @_on_connection
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
                raise TableError("No machine position present in status report."
                                 "Configure grbl!")
            position = tuple(float(p) for p in position)
        return status, position


    @_on_connection
    def home(self):
        """
        Starts the homing cycle. Blocks until finished.
        """
        self.serial_connection.command("$H", timeout=30)

    @_on_connection
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

    @_on_connection
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

    @_on_connection
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





# class Table:
#     """
#     Main interface for the usage of the table.

#     Coordinate system
#     -----------------
#     The coordinate system configured such that, in the top view on the table,
#     the origin is at the lower left corner, with x pointing to the right and y
#     pointing upwards.

#     Example
#     -------
#       >>> table = Table('COM3')
#       >>> table.connect()
#       >>> table.home()  # starts the homing cycle
#       >>> table.move(x=3, y=4, mode='absolute', feed='max')
#       >>> table.disconnect()
#     """
#     g_code = {'relative': 'G91',
#               'absolute': 'G90'}

#     def __init__(self, serial_port, baud_rate=115200):
#         self.serial_connection = SerialConnection(serial_port, baud_rate)
#         self._max_travel = None
#         self._max_feed = None
#         self._resolution = None

#     def connect(self):
#         """Connects to the serial port of the Arduino running grbl."""
#         self.serial_connection.connect()
#         response = self.serial_connection.serial_connection.read_all()
#         if response:
#             print("Grbl messages present:")
#             for line in response:
#                 print(line.decode('ascii'))
#         while True:
#             if self.is_alive() is True:
#                 self.serial_connection.serial_connection.read_all()
#                 return self.get_status()[0]
#             else:
#                 print("Grbl doesn't answer. Possible reasons could be:")
#                 print("  -- grbl is in an alarm state.")
#                 print("  -- grbl is too busy. (homing cycle, maybe?)")
#                 print("What do you want to do?\n")
#                 option = query_options(["Do a soft-reset.",
#                                         "Retry.",
#                                         "Abort."])
#                 if option == 1:
#                     self.reset()
#                 elif option == 2:
#                     pass
#                 elif option == 3:
#                     raise NotConnectedError

#     def is_alive(self):
#         self.serial_connection.serial_connection.read_all()
#         try:
#             self.serial_connection.command('', timeout=2)
#         except TimeOutError as error:
#             return False
#         else:
#             return True

#     def disconnect(self):
#         """Disconnects from the serial port."""
#         self.serial_connection.disconnect()

#     def reset(self):
#         """
#         Initiates a soft-reset.

#         Raises
#         ------
#         ResetError :
#             If reset is not successul.
#         """
#         self.serial_connection.serial_connection.write(b"r")
#         response = self.serial_connection.serial_connection.readlines()
#         if b"Grbl 1.1f ['$' for help]\r\n" in response:
#             print("Reset.")
#         else:
#             raise ResetError

#     def unlock(self):
#         """
#         Unlocks grbl for movements.

#         Raises
#         ------
#         UnlockError :
#             If unlock is not successful.
#         """
#         response = self.serial_connection.command("$X")
#         if '[MSG:Caution: Unlocked]' in response:
#             print("Unlocked.")
#         else:
#             raise UnlockError


#     def _get_property(self, ids):
#         response = self.serial_connection.command("$$")
#         for line in response:
#             if line.startswith("${}".format(ids[0])):
#                 _, x_prop = line.split("=")
#             if line.startswith("${}".format(ids[1])):
#                 _, y_prop = line.split("=")
#         return (float(x_prop), float(y_prop))


#     @property
#     def resolution(self):
#         """
#         Property resolution

#         Returns
#         -------
#         x_res, y_res : float
#             The resolution of each axis in steps/mm.
#         """
#         return self._get_property([100, 101])


#     @property
#     def max_travel(self):
#         """
#         Property max_travel

#         Returns
#         -------
#         x_max, y_max : float
#             The maximal travel distance of each axis in mm.
#         """
#         return self._get_property([130, 131])


#     @property
#     def max_feed(self):
#         """
#         Property max_feed

#         Returns
#         -------
#         feed_x_max, feed_y_max : float
#             The maximal feed of each axis in mm/min.
#         """
#         return self._get_property([110, 111])


#     def get_status(self):
#         """
#         Get the status of the device.

#         Returns
#         -------
#         status : string
#             The current state of the machine. Possible values:
#             Idle, Run, Hold, Jog, Alarm, Door, Check, Home, Sleep

#         position : tuple of floats
#             The current machine position.

#         Raises
#         ------
#         TableError :
#             if no machine position (MPos) is present in grbl status report.
#         """
#         response = self.serial_connection.command("?")[0]
#         response_fields = response.lower().strip("<>").split("|")
#         status = response_fields[0]
#         position = response_fields[1]
#         if position.startswith("mpos:"):
#             position = position[5:].split(",")[0:2]
#         else:
#             raise TableError("No machine position present in status report."
#                              "Configure grbl!")
#         position = tuple(float(p) for p in position)
#         return status, position

#     def home(self):
#         """
#         Starts the homing cycle. Blocks until finished.
#         """
#         self.serial_connection.command("$H")

#     def move(self, x, y, mode, feed='max'):
#         """
#         Moves the table to the desired coordinates.
#         Blocks until movement is finished.

#         Parameters
#         ----------
#         x, y : float
#             The coordinates to move to

#         feed : float
#             The feed rate in mm/min

#         mode : str {'relative', 'absolute'}
#             Move in relative or absolute coordinates.

#         Returns
#         -------
#         position : tuple of floats
#             The machine position after the movement.
#         """
#         mode = mode.lower()
#         if mode not in self.g_code.keys():
#             raise TableError("Invalid move mode.")
#         if feed == 'max':
#             feed = min(self.max_feed)
#         self.serial_connection.command("G1 {} X{} Y{} F{}".format(
#             self.g_code[mode], x, y, feed))
#         while True:
#             status, position = self.get_status()
#             if status.lower() == "idle":
#                 break
#             else:
#                 time.sleep(0.05)
#         return position

#     def interact(self):
#         """
#         Starts the interactive mode, where the user can directly communicate
#         with grbl.
#         """
#         print()
#         print("Interactive Mode:\n"
#               "=================\n\n"
#               "(q to quit, r to reset)")
#         history = []
#         while True:
#             command = input("---> ")
#             if command == 'q':
#                 return self.get_status()[1]
#             if command == 'r':
#                 self.reset()
#             if command.startswith('.'):
#                 if set(command) == {'.'}:
#                     i = command.count('.')
#                 command = history[-i]
#                 print("---> " + command)
#             history.append(command)
#             try:
#                 response = self.serial_connection.command(command)
#                 for line in response:
#                     print(line)
#             except GrblError as error:
#                 print(error)
#             except GrblAlarm as error:
#                 if error.i == '2':
#                     print(error)
#                     if query_yes_no("Unlock?"):
#                         self.reset()
#                         self.unlock()
#                     else:
#                         print("Staying in ALARM state ...")
#                 else:
#                     raise

#     def check_resolution(self, extent):
#         """
#         Checks if the grid points of the measuring area lie on the stepper motor
#         grid.

#         Parameters
#         ----------
#         extent : tuple {((x0, x1, delta_x), (y0, y1, delta_y))
#             The coordinates of the boundary points of the measuring area
#             (x0, x1, y0, y1) and the step size of each axis (delta_x, delta_y)

#         Raises
#         ------
#         NotOnGridError :
#             If specified scanning grid is not in accord with motor step size.
#         """
#         resolution = self.resolution
#         for res, ext in zip(resolution, extent):
#             for value in ext:
#                 if not round((res * value), 8).is_integer():
#                     message = ("extent value: {} mm; ".format(value) +
#                                "motor resolution: {} steps per mm".format(res))
#                     raise NotOnGridError(message)

#     def jog(self, x=0, y=0, feed=100, mode='relative'):
#         """
#         Move the table in jogging mode. Jogging mode doesn't alter the g-code
#         parser state. So parameters like feed rate or movement mode don't have
#         to be reset after jogging. Does *not* block until the movement is
#         finished.

#         Parameters
#         ----------
#         x, y : float
#             The coordinates to move to

#         feed : float
#             The feed rate in mm/min

#         mode : string, optional
#             Move in relative or absolute coordinates with ``relative`` or
#             ``absolute``
#         """
#         self.serial_connection.command("$J={} X{} Y{} F{}".format(
#             self.g_code[mode], x, y, feed))
