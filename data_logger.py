"""
This module provides an easy to use interface for control and data acquisition
of the Agilent data logger via its TCP SCPI port.
So far, only a temperature measurement on one channel is implemented.

Class listing
-------------
DataLoggerError :
    A simple exception class used for all errors in this module.
SCPISocket :
    An interface to the SCPI port of the data logger.
DataLogger :
    Main interface for the usage of the data logger

Notes
-----
The control of the data logger is performed via the class methods of
`DataLogger`. The class `SCPISocket` provides the low-level access to the TCP
SCPI port of the data logger. All end-user functionality of the interface is
implemented in class `DataLogger`, though.

Example
-------
  >>> data_logger = DataLogger('192.168.254.174')
  >>> with data_logger:
  >>>     data_logger.configure(channel=101)
  >>>     data_logger.display("EXAMPLE")
  >>>     data = data_logger.get_data()
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
        The SCPI port of the controller. Defaults to 5025.
    timeout : int, optional
        The time in seconds after which the socket stops trying to connect.
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
            msg = __("Could not connect to {} on SCPI port {}.", *self.address)
            logger.error(msg)
            raise DataLoggerError(msg)
        else:
            logger.debug(__("Connected to {} on SCPI port {}.", *self.address))

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
    Main interface for the usage of the data logger.

    Parameters
    ----------
    host : str
        The IP address of the data logger.
    scpi_port : int, optional
        The SCPI port of the data logger.

    Example
    -------
      >>> data_logger = DataLogger('192.168.254.174')
      >>> with data_logger:
      >>>     data_logger.configure(channel=101)
      >>>     data_logger.display("EXAMPLE")
      >>>     data = data_logger.get_data()
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
        """
        Configures the device to monitor (continuous measurement) the
        temperature.

        Parameters
        ----------
        channel : int
            The channel number to be monitored.
        """
        self._scpi_socket.command("*RST", get_response=False)
        self._scpi_socket.command("configure:temperature tc,k,(@{})".format(channel), get_response=False)
        self._scpi_socket.command("route:mon:chan (@{})".format(channel), get_response=False)
        self._scpi_socket.command("route:mon:stat on", get_response=False)

    @on_connection
    def get_data(self):
        """Queries and returns the current value of the monitored channel."""
        return self._scpi_socket.command("route:mon:data?")

    @on_connection
    def display(self, text):
        """Displays a custom text on the display."""
        self._scpi_socket.command("display:text '{}'".format(text), get_response=False)

    @on_connection
    def reset_display(self):
        """ Resets the display to the default."""
        self._scpi_socket.command("display:text:clear", get_response=False)

