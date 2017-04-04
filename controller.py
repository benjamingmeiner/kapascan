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
  >>> controller = Controller('192.168.254.173')
  >>> controller.connect()
  >>> with controller.acquisition(mode="continuous", sampling_time=50):
  >>>    controller.get_data(data_points=100, channels=(0,1))
  >>> controller.disconnect()
"""

import time
import socket
import struct
import telnetlib
from sensor import Sensor
import numpy as np
from contextlib import contextmanager

# TODO check all IO for exceptions that can be raised
# TODO use proper sensor class

class DeviceError(Exception):
    """Simple exception class used for all errors in this module."""

class UnknownCommandError(DeviceError):
    """Raise when an unknown command is sent to controller."""

class WrongParameterError(DeviceError):
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
        The time in seconds the socket stops to tries to connect.

    Example
    -------
      >>> control_socket =  ControlSocket('192.168.254.173')
      >>> control_socket.connect()
      >>> # prints the software version number
      >>> print(control_socket.command("VER"))
      >>> control_socket.disconnect()
    """
    def __init__(self, host, control_port=23, timeout=3):
        self.host = host
        self.control_port = control_port
        self.timeout = timeout
        self.control_socket = None

    def connect(self):
        """
        Open the connection to the telnet socket.

        Raises
        ------
        DeviceError :
            If the connection can not be established or closes unexpectedly.
        """
        self.control_socket = telnetlib.Telnet()
        try:
            self.control_socket.open(self.host, self.control_port, self.timeout)
        except OSError:
            raise DeviceError("Could not connect to {} on telnet port {}.".format(
                self.host, self.control_port))
        time.sleep(0.1)
        try:
            while self.control_socket.read_eager():
                pass
        except EOFError:
            raise DeviceError("Connection to {} closed unexpectedly.".format(
                self.host))

    def disconnect(self):
        """Close the connection to the telnet socket."""
        self.control_socket.close()

    def command(self, com):
        """
        Send a command to the controller.

        Parameters
        ----------
        com : string
            The command to be sent to the controller without the preceding '$'.

        Returns
        -------
        response : string
            The response of the device without the preceding command and
            trailing 'OK'.

        Raises
        ------
        DeviceError
            If the command is not known to the controller or a wrong parameter
            to a command is passed to the controller.
        """
        for seq in "\r\n":
            com = com.replace(seq, "")
        try:
            self.control_socket.write(b"$" + com.encode('ascii') + b"\r\n")
            time.sleep(0.1)
            response = self.control_socket.read_eager()
            response = response.decode('ascii').strip("\r\n")
        except (OSError, EOFError):
            raise DeviceError("Could not execute command {}".format(com))

        if response.startswith("$" + com):
            response = response[len(com) + 1:]
            if response.endswith("OK"):
                return response[:-2]
            elif response == "$UNKNOWN COMMAND":
                raise UnknownCommandError(com)
            elif response == "$WRONG PARAMETER":
                raise WrongParameterError(com)
        raise DeviceError("Unexpected response from device: {}".format(response))


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
        The time in seconds the socket stops to tries to connect.

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
    def __init__(self, host, data_port=10001, timeout=3):
        self.host = host
        self.data_port = data_port
        self.timeout = timeout
        self.data_socket = None

    def connect(self):
        """
        Open a new data socket. Data acquisition starts as soon as the socket is
        connected.

        Raises
        ------
        DeviceError :
            If the connection can not be established.
        """
        self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_socket.settimeout(self.timeout)
        try:
            self.data_socket.connect((self.host, self.data_port))
        except OSError:
            raise DeviceError("Could not connect to {} on data port {}.".format(
                self.host, self.data_port))

    def disconnect(self):
        """Close the connection to the data socket."""
        self.data_socket.close()

    def inspect_header(self, data_stream):
        """
        Inspect the header of the data packages sent by the controller.

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

    def get_data(self, data_points, channels):
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
        A n x m array where n = number of channels and m = number of data points.

        Raises
        ------
        DeviceError :
            If the number of requested channels is larger than the actual
            channel number.
        """
        channels = list(channels)
        data_stream = b''
        dtype = np.dtype(int).newbyteorder('<')
        data = np.zeros((data_points, len(channels)), dtype)
        received_points = 0
        while received_points < data_points:
            while len(data_stream) < 32:
                try:
                    data_stream += self.data_socket.recv(65536)
                except socket.timeout:
                    print("ERROR: No data available.")
                    return data
            nr_of_channels, nr_of_frames, bytes_per_frame, frame_counter = \
                self.inspect_header(data_stream)
#            if received_points != frame_counter - 1:
#                print(received_points)
#                print(frame_counter)
#                raise DeviceError("Missed frames!")
            payload_size = bytes_per_frame * nr_of_frames
            if max(channels) + 1 > nr_of_channels:
                raise DeviceError("Device has only {} channels.".format(
                    nr_of_channels))
            while len(data_stream) < 32 + payload_size:
                data_stream += self.data_socket.recv(65536)
            payload = data_stream[32:32 + payload_size]
            for i in range(nr_of_frames):
                if received_points < data_points:
                    frame = payload[i*bytes_per_frame:(i+1)*bytes_per_frame]
                    data[received_points] = np.frombuffer(frame, dtype)[channels]
                    received_points += 1
                else:
                    break
            data_stream = data_stream[32+payload_size:]
        if len(channels) == 1:
            return data.T[0]
        else:
            return data.T


class Controller:
    """
    Main interface for the usage of the controller.

    Parameters
    ----------
    sensor : class Sensor
        A Sensor class as defined in sensor.py.
    host : str
        The hosts IP address
    control_port : int, optional
        The telnet port of the controller.
    data_port : int, optional
        The data port of the controller.

    Example
    -------
      >>> controller = Controller('192.168.254.173')
      >>> controller.connect()
      >>> with controller.acquisition(mode="continuous", sampling_time=50):
      >>>    controller.get_data(data_points=100, channels=(0,1))
      >>> controller.disconnect()
    """
    def __init__(self, host, control_port=23, data_port=10001, 
                 sensor=Sensor('1234')):
        self.sensor = sensor
        self.control_socket = ControlSocket(host, control_port)
        self.data_socket = DataSocket(host, data_port)
        self.status_response = None

    def connect(self):
        """
        Connect to the control socket of the controller. The data socket
        is not connected until the actual measurement.
        """
        self.control_socket.connect()

    def disconnect(self):
        """Disconnect from the control socket of the controller."""
        self.control_socket.disconnect()

    def set_sampling_time(self, sampling_time):
        """
        Set the sampling time to the closest possible sampling time of the
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
        actual_time = response.strip(",")
        print("Set sampling time: {} ms".format(float(actual_time) / 1000))
        return actual_time

    def set_trigger_mode(self, mode):
        """
        Set the trigger mode.

        Parameters
        ----------
        mode : str {'continuous', 'rising_edge', 'high_level', 'gate_rising_edge'}
            See manual for an explanation of the modes.
        """
        trg_nr = {"continuous": 0, "rising_edge": 1,
                  "high_level": 2, "gate_rising_edge": 3}
        response = self.control_socket.command("TRG{}".format(trg_nr[mode]))

    def check_status(self):
        """
        Check all relevant measurement parameters of the controller.

        This methods queries the status of the controller and compares it to the
        previous status that was saved as an attribute. It prints out a warning
        if the status changed between to subsequent calls.
        """
        response1 = self.control_socket.command("STS")
        response2 = self.control_socket.command("LIN?")
        status_response = response1 + ";LIN" + response2
        if self.status_response is not None:
            status_new = status_response.split(';')
            status_old = self.status_response.split(';')
            for new, old in zip(status_new, status_old):
                if new != old:
                    print("WARNING: "
                          "Changed parameter: {} to {}.".format(old, new))
        self.status_response = status_response

    def trigger(self):
        """ Trigger a single measurement."""
        self.control_socket.command("GMD")

    def get_data(self, data_points=1, channels=(0, 1)):
        """
        Get data from controller. All channels are measured simultaneously.

        Parameters
        ----------
        data_points : int, optional
            number of data points to be measured (per channel).
        channels : list of ints, optional
            A list of the channels to get the data from.
        """
        return self.scale(self.data_socket.get_data(data_points, channels))

    def scale(self, data):
        """Scale the acquired data to the measuring range of the sensor."""
        return data / 0xffffff * self.sensor.range

    @contextmanager
    def acquisition(self, mode=None, sampling_time=None):
        """
        Start the actual data acquisition by connecting to the data socket.

        Parameters
        ----------
        mode : str {'continuous', 'rising_edge', 'high_level', 'gate_rising_edge'}
            The trigger mode.
        sampling_time : float
            The desired sampling time in ms. The controller automatically
            chooses the closest possible sampling time.
        """
        try:
            if mode:
                self.set_trigger_mode(mode)
            if sampling_time:
                self.set_sampling_time(sampling_time)
            self.data_socket.connect()
            yield
        finally:
            self.data_socket.disconnect()

