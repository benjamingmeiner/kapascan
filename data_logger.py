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

# TODO: document timeout behaveour.

import socket
import logging
from .base import IOBase, Device, on_connection
from .helper import BraceMessage as __

logger = logging.getLogger(__name__)


class DataLoggerError(Exception):
    """Simple exception class used for all errors in this module."""

class SCPISocket(IOBase):
    """
    Interface to the TCP SCPI socket of the data logger.

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

    def __init__(self, host, scpi_port=5025):
        super().__init__((host, scpi_port))
        self.socket = None

    def _open(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.socket.settimeout(self.timeout)
        try:
            self.socket.connect(self.address)
        except OSError:
            msg = __("Could not connect to {} on scpi port {}.", *self.address)
            logger.error(msg)
            raise DataLoggerError(msg)
        else:
            logger.debug(__("Connected to {} on scpi port {}.", *self.address))

    def _close(self):
        self.socket.close()
        logger.debug(__("Disconnected from {}:{}.", *self.address))

    def _send(self, cmd):
        cmd += "\n"
        logger.debug(__("Sending: {!r}", cmd))
        cmd = cmd.encode('ascii')
        sent_bytes = 0
        while sent_bytes < len(cmd):
            sent = self.socket.send(cmd[sent_bytes:])
            if sent == 0:
                msg = __("{}:{}: SCPI socket broken.", *self.address)
                logger.error(msg)
                raise DataLoggerError(msg)
            sent_bytes += sent

    def _receive(self):
        try:
            data = self.socket.recv(65536).decode('ascii')
            logger.debug(__("Received: {!r}", data))
            return data
        except socket.timeout:
            return None


class DataLogger(Device):
    """
    bla
    """

    def __init__(self, host, scpi_port=5025):
        super().__init__()
        self._scpi_socket = SCPISocket(host, scpi_port)

    def _connect(self):
        self._scpi_socket.connect()

    def _disconnect(self):
        self.reset_display()
        self._scpi_socket.disconnect()

    @on_connection
    def configure(self, channel):
        self._scpi_socket.command("*RST", get_response=False)
        self._scpi_socket.command("configure:temperature tc,k,(@{})".format(channel), get_response=False)
        self._scpi_socket.command("route:mon:chan (@{})".format(channel), get_response=False)
        self._scpi_socket.command("route:mon:stat on", get_response=False)

    @on_connection
    def get_data(self):
        return self._scpi_socket.command("route:mon:data?")

    @on_connection
    def reset_display(self):
        self._scpi_socket.command("display:text:clear", get_response=False)

    @on_connection
    def display(self, text):
        self._scpi_socket.command("display:text '{}'".format(text), get_response=False)

