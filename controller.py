"""
This module provides an easy to use interface for control and data acquisition
of the Micro-Epsilon DT6220 controller.

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
import logging
import queue
import numpy as np
from .sensor import SENSORS
from .base import IOBase, Device, on_connection
from .helper import BraceMessage as __

# TODO check all IO for exceptions that can be raised
# TODO use frame counter
# TODO use proper custom exceptions
# TODO refactor errors (less)

logger = logging.getLogger(__name__)

class ControllerError(Exception):
    """Simple exception class used for all errors in this module."""


class UnknownCommandError(ControllerError):
    """Raise when an unknown command is sent to controller."""


class WrongParameterError(ControllerError):
    """Raise when a command with a wrong parameter is sent to the controller."""


class ControlSocket(IOBase):
    """
    Interface to the telnet port of the controller.

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

    def __init__(self, host, control_port=23):
        super().__init__((host, control_port))
        self.socket = None

    def _open(self):
        self.socket = telnetlib.Telnet()
        try:
            self.socket.open(*self.address, self.timeout)
        except OSError:
            msg = __("Could not connect to {} on telnet port {}.", *self.address)
            logger.error(msg)
            raise ControllerError(msg)
        else:
            logger.debug(__("Connected to {} on telnet port {}.", *self.address))
        time.sleep(0.1)
        try:
            while self.socket.read_eager():
                pass
        except EOFError:
            msg = __("Connection to {}:{} closed unexpectedly.", *self.address)
            logger.error(msg)
            raise ControllerError(msg)

    def _close(self):
        self.socket.close()
        logger.debug(__("Disconnected from {}:{}.", *self.address))

    def _send(self, cmd):
        for seq in "\r\n":
            cmd = cmd.replace(seq, "")
        cmd = "$" + cmd + "\r\n"
        logger.debug(__("Sending: {!r}",  cmd))
        self.socket.write(cmd.encode('ascii'))

    def _receive(self):
        line = self.socket.read_until(b"\n", timeout=self.timeout).decode('ascii')
        if line:
            logger.debug(__("Received: {!r}", line))
            line = line.strip("\r\n")
            return line
        else:
            return None

    def get_answer(self, timeout=None):
        line = self._get_item(timeout)
        #TODO strip error message from line for proper logging entry
        if "$UNKNOWN COMMAND" in line:
            logger.error(line)
            raise ControllerError(line)
        if "$WRONG PARAMETER" in line:
            logger.error(line)
            raise ControllerError(line)
        if line.endswith("OK"):
            return line[:-2]
        else:
            msg = __("Unexpected response: {!r}.", line)
            logger.error(msg)
            raise ControllerError(msg)

    def command(self, cmd):
        return super().command(cmd, get_response=True)[len(cmd) + 1:]


class DataSocket(IOBase):
    """
    Interface to the data port of the controller.

    Parameters
    ----------
    host : string
        The hosts IP address.
    data_port : int, optional
        The data port of the controller.

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

    Data Representation
    -------------------
    The controller sends data packages with the following structure:

    ================ ============ =============================================
    part             size (bytes) encoding
    ================ ============ =============================================
    preamble          4           ASCII
    item nr.          4           int
    serial nr.        4           int
    channels          8           bit field; two bytes per channel;
                                  01: channel present, 00: channel not present;
                                  => n = number of channels
    unused            4
    bytes per frame   2           short
    number of frames  2           short
    frame counter     4           int
    frame 1           n * 4       n * int
    frame 2           n * 4       n * int
    ...               ...         ...
    ================ ============ =============================================
    """

    def __init__(self, host, data_port=10001, timeout=2):
        super().__init__((host, data_port), timeout, do_input=True, do_output=False)
        self._socket = None

    def _open(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(self.timeout)
        try:
            self._socket.connect(self.address)
        except OSError:
            msg = __("Could not connect to {} on data port {}.", *self.address)
            logger.error(msg)
            raise ControllerError(msg)
        else:
            logger.debug(__("Connected to {} on data port {}.", *self.address))

    def _close(self):
        self._socket.close()
        logger.debug(__("Disconnected from {}:{}.", *self.address))

    def _receive(self):
        try:
            data = self._socket.recv(65536)
            logger.debug(__("Received: {!r}", data))
            return data
        except socket.timeout:
            return None

    def get_data(self, data_points, sensors):
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
                msg = "You have specified sensors that are" + \
                      " connected to the same demodulator."
                logger.error(msg)
                raise ControllerError(msg)
        logger.debug(__("Getting {} data points from channels {} ...",
                        data_points, channels))
        data_stream = b''
        dtype = np.dtype(np.int32).newbyteorder('<')
        data = np.zeros((data_points, len(channels)), dtype)
        received_points = 0
        while received_points < data_points:
            while len(data_stream) < 32:
                data_stream += self.in_queue.get()
            nr_of_channels, nr_of_frames, bytes_per_frame, frame_counter = \
                self._parse_header(data_stream)
            # TODO frame counter check
            # if received_points != frame_counter - 1:
            #     print(received_points)
            #     print(frame_counter)
            #     raise DeviceError("Missed frames!")
            payload_size = bytes_per_frame * nr_of_frames
            if max(channels) + 1 > nr_of_channels:
                msg = __("Device has only {} channels.", nr_of_channels)
                logger.error(msg)
                raise ControllerError(msg)
            while len(data_stream) < 32 + payload_size:
                data_stream += self.in_queue.get()
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
        return data.T

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


class Controller(Device):
    """
    Main interface for the usage of the controller.

    Parameters
    ----------
    sensors : list of str
        The serial numbers of the sensors to be measured with as defined in
        sensor.py.
    host : str
        The hosts IP address
    control_port : int, optional
        The telnet port of the controller.
    data_port : int, optional
        The data port of the controller.

    Example
    -------
      >>> controller = Controller(['2011'], '192.168.254.173')
      >>> with controller:
      >>>    data = controller.get_data(
      >>>         data_points=100, mode="continuous", sampling_time=50)
    """

    def __init__(self, sensors, host, control_port=23, data_port=10001):
        self.sensors = [SENSORS[sensor] for sensor in sensors]
        self.control_socket = ControlSocket(host, control_port)
        self.data_socket = DataSocket(host, data_port)
        self.status_response = None

    def _connect(self):
        self.control_socket.connect()

    def _disconnect(self):
        self.control_socket.disconnect()

    @on_connection
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
            logger.warning(__("Requested sampling time: {} ms; Set sampling time: {} ms", actual_time / 1000))
        return actual_time

    @on_connection
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

    @on_connection
    def trigger(self):
        """ Trigger a single measurement."""
        self.control_socket.command("GMD")

    def scale(self, data):
        """Scales the acquired data to the measuring range of the sensor."""
        scaled_data = np.zeros_like(data, dtype=np.float64)
        for i, (sensor, channel_data) in enumerate(zip(self.sensors, data)):
           scaled_data[i] = channel_data / 0xffffff * sensor['range']
        return scaled_data

    def acquire(self, data_points=1, mode=None, sampling_time=None):
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
        try:
            self.data_socket.connect()
            data = self.data_socket.get_data(data_points, self.sensors)
            return self.scale(data)
        finally:
            self.data_socket.disconnect()
