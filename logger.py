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
  >>> controller = Controller('2011', '192.168.254.173')
  >>> controller.connect()
  >>> with controller.acquisition(mode="continuous", sampling_time=50):
  >>>    controller.get_data(data_points=100, channels=(0,1))
  >>> controller.disconnect()
"""

import time
import socket
import struct
import telnetlib
import numpy as np
from contextlib import contextmanager


class LoggerError(Exception):
    """Simple exception class used for all errors in this module."""

class SCPISocket:
    """
    Interface to the TCP SCPI socket of the Data Logger.

    Parameters
    ----------
    host : string
        The hosts IP address.
    scpi_port : int, optional
        The data port of the controller.
    timeout : int, optional
        The time in seconds after which the socket stops trying to connect.

    Example
    -------
      >>>
      >>>
      >>>
    """

    def __init__(self, host, scpi_port=5025, timeout=3):
        self.host = host
        self.scpi_port = scpi_port
        self.timeout = timeout
        self.scpi_socket = None

    def connect(self):
        """
        Open a new scpi socket. Data acquisition starts as soon as the socket is
        connected.

        Raises
        ------
        DeviceError :
            If the connection can not be established.
        """
        self.scpi_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.scpi_socket.settimeout(self.timeout)
        try:
            self.scpi_socket.connect((self.host, self.scpi_port))
        except OSError:
            raise LoggerError("Could not connect to {} on scpi port {}.".format(
                self.host, self.scpi_port))

    def disconnect(self):
        """Close the connection to the scpi socket."""
        self.scpi_socket.close()

    def command(self, com):
        total_sent = 0
        encoded_com = com.encode('ascii') + b"\n"
        while total_sent < len(encoded_com):
            sent = self.scpi_socket.send(encoded_com[total_sent:])
            if sent == 0:
                raise LoggerError("SCPI Socket connection broken.")
            total_sent += sent


#class Controller:
#    """
#    Main interface for the usage of the controller.
#
#    Parameters
#    ----------
#    sensor : str
#        The serial number of the sensor as defined in sensor.py.
#    host : str
#        The hosts IP address
#    control_port : int, optional
#        The telnet port of the controller.
#    data_port : int, optional
#        The data port of the controller.
#
#    Example
#    -------
#      >>> controller = Controller('2011', '192.168.254.173')
#      >>> controller.connect()
#      >>> with controller.acquisition(mode="continuous", sampling_time=50):
#      >>>    controller.get_data(data_points=100, channels=(0,1))
#      >>> controller.disconnect()
#    """
#
#    def __init__(self, sensor, host, control_port=23, data_port=10001):
#        self.sensor = SENSORS[sensor]
#        self.control_socket = ControlSocket(host, control_port)
#        self.data_socket = DataSocket(host, data_port)
#        self.status_response = None
#
#    def __enter__(self):
#        return self.connect()
#
#    def __exit__(self, *args):
#        self.disconnect()
#
#    def connect(self):
#        """
#        Connect to the control socket of the controller. The data socket
#        is not connected until the actual measurement.
#        """
#        self.control_socket.connect()
#        return self
#
#    def disconnect(self):
#        """Disconnect from the control socket of the controller."""
#        self.control_socket.disconnect()
#
#    def set_sampling_time(self, sampling_time):
#        """
#        Set the sampling time to the closest possible sampling time of the
#        controller.
#
#        Parameters
#        ----------
#        sampling_time : float
#            The desired sampling time in ms.
#
#        Returns
#        -------
#        actual_time : float
#            The actual sampling time.
#        """
#        sampling_time = int(sampling_time * 1000)
#        response = self.control_socket.command("STI{}".format(sampling_time))
#        actual_time = int(response.strip(","))
#        if actual_time != sampling_time:
#            print("Set sampling time: {} ms".format(actual_time / 1000))
#        return actual_time
#
#    def set_trigger_mode(self, mode):
#        """
#        Set the trigger mode.
#
#        Parameters
#        ----------
#        mode : str {'continuous', 'rising_edge', 'high_level', 'gate_rising_edge'}
#            See manual for an explanation of the modes.
#        """
#        trg_nr = {"continuous": 0, "rising_edge": 1,
#                  "high_level": 2, "gate_rising_edge": 3}
#        self.control_socket.command("TRG{}".format(trg_nr[mode]))
#
#    def check_status(self):
#        """
#        Check all relevant measurement parameters of the controller.
#
#        This methods queries the status of the controller and compares it to the
#        previous status that was saved as an attribute. It prints out a warning
#        if the status changed between to subsequent calls.
#        """
#        response1 = self.control_socket.command("STS")
#        response2 = self.control_socket.command("LIN?")
#        status_response = response1 + ";LIN" + response2
#        if self.status_response is not None:
#            status_new = status_response.split(';')
#            status_old = self.status_response.split(';')
#            for new, old in zip(status_new, status_old):
#                if new != old:
#                    print("WARNING: "
#                          "Changed parameter: {} to {}.".format(old, new))
#        self.status_response = status_response
#
#    def trigger(self):
#        """ Trigger a single measurement."""
#        self.control_socket.command("GMD")
#
#    def get_data(self, data_points=1, channels=(0, 1)):
#        """
#        Get data from controller. All channels are measured simultaneously.
#
#        Parameters
#        ----------
#        data_points : int, optional
#            number of data points to be measured (per channel).
#        channels : list of ints, optional
#            A list of the channels to get the data from.
#        """
#        return self.scale(self.data_socket.get_data(data_points, channels))
#
#    def scale(self, data):
#        """Scale the acquired data to the measuring range of the sensor."""
#        return data / 0xffffff * self.sensor['range']
#
#    @contextmanager
#    def acquisition(self, mode=None, sampling_time=None):
#        """
#        Start the actual data acquisition by connecting to the data socket.
#
#        Parameters
#        ----------
#        mode : str {'continuous', 'rising_edge', 'high_level', 'gate_rising_edge'}
#            The trigger mode.
#        sampling_time : float
#            The desired sampling time in ms. The controller automatically
#            chooses the closest possible sampling time.
#        """
#        try:
#            if mode:
#                self.set_trigger_mode(mode)
#            if sampling_time:
#                self.set_sampling_time(sampling_time)
#            self.data_socket.connect()
#            yield
#        finally:
#            self.data_socket.disconnect()
