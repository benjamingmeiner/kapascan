"""
This module provides an easy to use interface for control and data acquisition
of the DT6220 Controller.

Class listing
-------------
ControlSocket :
    An interface to the Telnet port of the controller.
DataSocket :
    An interface to the data port of the controller.
Controller :
    Main interface for the usage of the controller

Notes
-----
Data acquisition and control of various parameters of the controller is
performed via the class methods of ``Controller``. The classes ``ControlSocket``
and ``DataSocket`` provide the low-level access to the control and data port of
the device. All end-user functionality of the interface is implemented in class
``Controller``, though.

Example
-------
  >>> controller = Controller(['2011'], '192.168.254.173')
  >>> with controller:
  >>>     controller.start_acquisition(data_points=100,
  >>>                                  mode="continuous",
  >>>                                  sampling_time=50)
  >>>     data = controller.stop_acquisition()
"""

import time
import socket
import struct
import telnetlib
import queue
import threading
from functools import wraps
from contextlib import contextmanager
from .sensor import SENSORS
import numpy as np

# TODO check all IO for exceptions that can be raised
# TODO check status responses from device for errors
# TODO use frame counter

# TODO name threads
# TODO Implement NotConnectedError
# TODO pass exceptions from I/O threds to main thread?

class ControllerError(Exception):
    """Simple exception class used for all errors in this module."""


class UnknownCommandError(ControllerError):
    """Raise when an unknown command is sent to controller."""


class WrongParameterError(ControllerError):
    """Raise when a command with a wrong parameter is sent to the controller."""


class ControlSocket:
    """
    Interface to the Telnet port of the controller.

    An overview of all commands that can be sent to the controller can be found
    in chapter 6.4 of the manual.

    Parameters
    ----------
    host : string
        The hosts ip address.
    control_port : int, optional
        The telnet port of the controller.
    timeout : int, optional
        The time in seconds the socket stops trying to connect.

    Example
    -------
      >>> control_socket =  ControlSocket('192.168.254.173')
      >>> control_socket.connect()
      >>> # prints the software version number
      >>> print(control_socket.command("VER"))
      >>> control_socket.disconnect()
    """

    def __init__(self, host, control_port=23, timeout=2):
        self.host = host
        self.control_port = control_port
        self.timeout = timeout
        self.control_socket = None
        self.io_threads = []
        self.out_queue = queue.Queue()
        self.in_queue = queue.Queue()
        self._stop_flag = False

    def connect(self):
        """
        Open the connection to the telnet socket and starts the I/O threads.

        Raises
        ------
        ControllerError :
            If the connection can not be established or closes unexpectedly.
        """
        if not self.io_threads:
            self._stop_flag = False
            self.control_socket = telnetlib.Telnet()
            try:
                self.control_socket.open(self.host, self.control_port, self.timeout)
            except OSError:
                raise ControllerError("Could not connect to "
                    "{} on telnet port {}.".format(self.host, self.control_port))
            time.sleep(0.1)
            try:
                while self.control_socket.read_eager():
                    pass
            except EOFError:
                raise ControllerError("Connection to "
                    "{} closed unexpectedly.".format(self.host))
            targets = (self._input, self._output)
            for target in targets:
                thread = threading.Thread(target=target, args=(self._stop,))
                self.io_threads.append(thread)
                thread.start()

    def disconnect(self):
        """Closes the telnet socket and stops the I/O threads."""
        self._stop_flag = True
        for thread in self.io_threads:
            thread.join()
        self.io_threads.clear()
        self.control_socket.close()

    def _stop(self):
        return self._stop_flag

    def _output(self, stop):
        """
        The target function of the output thread. Gets the commands to write
        from out_queue and writes the to the telnet socket.

        Parameters
        ----------
        stop: function
            The thread runs as long as the function call evaluates to True.
        """
        while not stop():
            try:
                cmd = self.out_queue.get(timeout=self.timeout)
            except queue.Empty:
                continue
            for seq in "\r\n":
                cmd = cmd.replace(seq, "")
            cmd = b"$" + cmd.encode('ascii') + b"\r\n"
            self.control_socket.write(cmd)

    def _input(self, stop):
        while not stop():
            line = self.control_socket.read_until(b"\n", timeout=self.timeout)
            if line:
                line = line.decode('ascii').strip("\r\n")
                if "$UNKNOWN COMMAND" in line:
                    raise UnknownCommandError()
                if "$WRONG PARAMETER" in line:
                    raise WrongParameterError()
                if line.endswith("OK"):
                    self.in_queue.put(line[:-2])
                else:
                    raise ControllerError(
                        "Unexpected response: '{}'".format(line))

    def command(self, cmd):
        """
        Send a command to the controller.

        Parameters
        ----------
        com : string
            The command to be sent to the controller without the preceding '$'.

        Returns
        -------
        answer : string
            The response of the device without the preceding command and
            trailing 'OK'.
        """
        self.out_queue.put(cmd)
        try:
            answer = self.in_queue.get(timeout=self.timeout)
        except queue.Empty:
            raise ControllerError(
                "No response to command '{}'. ".format(cmd) + 
                "I/O threads and controller still alive?")
        if answer.startswith("$" + cmd):
            return answer[len(cmd) + 1:]
        else:
            raise ControllerError(
                "Unexpected response '{}' on command '{}'.".format(answer, cmd))

class DataSocket:
    """
    Interface to the data port of the controller.

    Parameters
    ----------
    host : string
        The hosts IP address.
    data_port : int, optional
        The data port of the controller.
    timeout : int, optional
        The time in seconds after which the socket stops to trying to connect.

    Example
    -------
      >>> data_socket = DataSocket(host)
      >>> data_socket.connect()
      >>> data = data_socket.get_data(data_points, channels)
      >>> data_socket.disconnect()

    Notes
    -----
    As soon as the data socket is established (via method ``connect``) data
    acquisition is started. Available data is transmitted immediatelye. If
    the controller is set to trigger mode "continuous", data will be available
    with the sampling frequency. If the controller is set to one of the other
    trigger modes, data will be available not until a signal is present at the
    trigger input, or the command "GDM" is sent over the control port.

    The transmitted data is stored in a socket buffer which is handled by the
    operating system. You can fetch this buffered data via method ``get_data``.
    If you don't fetch the buffered data, the buffer may overflow and further
    data acquisition is interrupted.

    When ``data_port`` is different from the standard port 10001, it can be
    retrieved via the control command "GDP"
      >>> control_socket = ControlSocket(host)
      >>> control_socket.connect()
      >>> data_port = control_socket.command("GDP")
      >>> control_socket.disconnect()

    Data Representation
    -------------------
    The controller sends data packages with the following structure:

    ================ ============ =============================================
    part             size (bytes) encoding
    ================ ============ =============================================
    preamble          4           ASCII
    item nr.          4           int
    serial nr.        4           int
    channels          8           bit field; two bits per channel;
                                  01: channel present, 00: channel not present;
                                  => n = number of channels
    unused            4
    number of frames  2           short
    bytes per frame   2           short
    frame counter     4           int
    frame 1           n * 4       n * int
    frame 2           n * 4       n * int
    ...               ...         ...
    ================ ============ =============================================
    """

    def __init__(self, host, data_port=10001, timeout=2):
        self.host = host
        self.data_port = data_port
        self.timeout = timeout
        self.data_socket = None
        self.in_thread = None
        self.in_queue = queue.Queue()
        self._stop_flag = False

    def acquire(self, data_points, sensors):
        """
        Open a new data socket. Data acquisition starts as soon as the socket is
        connected.

        Raises
        ------
        DeviceError :
            If the connection can not be established.
        """
        if not self.in_thread:
            self._stop_flag = False
            self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.data_socket.settimeout(self.timeout)
            try:
                self.data_socket.connect((self.host, self.data_port))
            except OSError:
                raise ControllerError("Could not connect to {} on port {}.".format(
                    self.host, self.data_port))
            self.in_thread = threading.Thread(target=self._get_data,
                                              args=(data_points, sensors))
            self.in_thread.start()

    def end(self):
        """Close the connection to the data socket."""
        self._stop_flag = True
        self.in_thread.join()
        self.in_thread = None
        self.data_socket.close()

    def _get_data(self, data_points, sensors):
        """
        Get measurement data from the controller.

        Parameters
        ----------
        data_points : int
            The number of data points to be received.
        channels : list of ints
            A list of the channels to get the data from.

        Returns
        -------
        An n x m array where n = number of channels and m = number of data points.

        Raises
        ------
        DeviceError :
            If the number of requested channels is larger than the actual
            channel number.
        """
        channels = []
        for sensor in sensors:
            channel = sensor['channel']
            if channel not in channels:
                channels.append(channel)
            else:
                raise ControllerError("You have specified sensors that are" +
                    " connected to the same demodulator")
        data_stream = b''
        dtype = np.dtype(np.int32).newbyteorder('<')
        data = np.zeros((data_points, len(channels)), dtype)
        received_points = 0
        while received_points < data_points:
            while len(data_stream) < 32:
                data_stream += self._wait_for_data()
            nr_of_channels, nr_of_frames, bytes_per_frame, frame_counter = \
                self._parse_header(data_stream)
#            if received_points != frame_counter - 1:
#                print(received_points)
#                print(frame_counter)
#                raise DeviceError("Missed frames!")
            payload_size = bytes_per_frame * nr_of_frames
            if max(channels) + 1 > nr_of_channels:
                raise ControllerError("Device has only {} channels.".format(
                    nr_of_channels))
            while len(data_stream) < 32 + payload_size:
                data_stream += self._wait_for_data()
            payload = data_stream[32:32 + payload_size]
            for i in range(nr_of_frames):
                if received_points < data_points:
                    frame = payload[i * bytes_per_frame:
                                    (i + 1) * bytes_per_frame]
                    data[received_points] = np.frombuffer(frame, dtype)[channels]
                    received_points += 1
                else:
                    break
            data_stream = data_stream[32 + payload_size:]
        if len(channels) == 1:
            self.in_queue.put(data.T)
        else:
            self.in_queue.put(data.T)

    def _wait_for_data(self):
        while True:
            try:
                return self.data_socket.recv(65536)
            except socket.timeout:
                continue

    def _parse_header(self, data_stream):
        """
        Parse the header of the data packages sent by the controller.

        Parameters
        ----------
        data_stream : bytes
            The data stream as returned by socket.recv(buffsize).

        Returns
        -------
        nr_of_channels, nr_of_frames, bytes_per_frame, payload_size : int
            The values extracted from the header.
        """
        header = struct.unpack('<iiiqihhi', data_stream[0:32])
        channel_field = header[3]
        nr_of_channels = '{0:064b}'.format(channel_field).count('1')
        nr_of_frames = header[6]
        bytes_per_frame = header[5]
        frame_counter = header[7]
        return nr_of_channels, nr_of_frames, bytes_per_frame, frame_counter


class Controller:
    """
    Main interface for the usage of the controller.

    Parameters
    ----------
    sensor : str
        The serial number of the sensor as defined in sensor.py.
    host : str
        The hosts IP address
    control_port : int, optional
        The telnet port of the controller.
    data_port : int, optional
        The data port of the controller.

    Example
    -------
      >>> controller = Controller('2011', '192.168.254.173')
      >>> controller.connect()
      >>> with controller.acquisition(mode="continuous", sampling_time=50):
      >>>    controller.get_data(data_points=100, channels=(0,1))
      >>> controller.disconnect()
    """

    def __init__(self, sensors, host, control_port=23, data_port=10001):
        self.sensors = [SENSORS[sensor] for sensor in sensors]
        self.control_socket = ControlSocket(host, control_port)
        self.data_socket = DataSocket(host, data_port)
        self.status_response = None
        self.connected = False

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.disconnect()

    def connect(self):
        """
        Connects to the control socket of the controller. The data socket
        is not connected until the actual measurement.
        """
        self.control_socket.connect()
        self.connected = True
        return self

    def disconnect(self):
        """Disconnect from the control socket of the controller."""
        self.control_socket.disconnect()
        self.connected = False

    def _on_connection(f):
        @wraps(f)
        def checked(self, *args, **kwargs):
            if self.connected:
                return f(self, *args, **kwargs)
            else:
                raise NotConnectedError
        return checked

    @_on_connection
    def set_sampling_time(self, sampling_time):
        """
        Sets the sampling time to the closest possible sampling time of the
        controller.

        Parameters
        ----------
        sampling_time : float
            The desired sampling time in ms.

        Returns
        -------
        actual_time : float
            The actual sampling time.
        """
        sampling_time = int(sampling_time * 1000)
        response = self.control_socket.command("STI{}".format(sampling_time))
        actual_time = int(response.strip(","))
        if actual_time != sampling_time:
            print("Set sampling time: {} ms".format(actual_time / 1000))
        return actual_time

    @_on_connection
    def set_trigger_mode(self, mode):
        """
        Sets the trigger mode.

        Parameters
        ----------
        mode : str {'continuous', 'rising_edge', 'high_level', 'gate_rising_edge'}
            See manual for an explanation of the modes.
        """
        trg_nr = {"continuous": 0, "rising_edge": 1,
                  "high_level": 2, "gate_rising_edge": 3}
        self.control_socket.command("TRG{}".format(trg_nr[mode]))

    @_on_connection
    def trigger(self):
        """ Trigger a single measurement."""
        self.control_socket.command("GMD")

    def scale(self, data):
        """Scales the acquired data to the measuring range of the sensor."""
        scaled_data = np.zeros_like(data, dtype=np.float64)
        for i, (sensor, channel_data) in enumerate(zip(self.sensors, data)):
           scaled_data[i] = channel_data / 0xffffff * sensor['range']
        return scaled_data

    def start_acquisition(self, data_points=1, mode=None, sampling_time=None):
        """
        Starts the actual data acquisition by connecting to the data socket. All
        channels are measured simultaneously.

        Parameters
        ----------
        data_points : int, optional
            number of data points to be measured (per channel).
        channels : list of ints, optional
            A list of the channels to get the data from.
        mode : str {'continuous', 'rising_edge', 'high_level', 'gate_rising_edge'}
            The trigger mode.
        sampling_time : float
            The desired sampling time in ms. The controller automatically
            chooses the closest possible sampling time.
        """
        if mode:
            self.set_trigger_mode(mode)
        if sampling_time:
            self.set_sampling_time(sampling_time)
        self.data_socket.acquire(data_points, self.sensors)

    def stop_acquisition(self):
        self.data_socket.end()
        try:
            data = self.scale(self.data_socket.in_queue.get_nowait())
        except queue.Empty:
            raise NoDataAcquired
        return data

