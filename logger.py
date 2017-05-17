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
        Open a new scpi socket.

        Raises
        ------
        LoggerError :
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

    def send(self, com):
        total_sent = 0
        encoded_com = com.encode('ascii') + b"\n"
        while total_sent < len(encoded_com):
            sent = self.scpi_socket.send(encoded_com[total_sent:])
            if sent == 0:
                raise LoggerError("SCPI Socket connection broken.")
            total_sent += sent

    def receive(self):
        try:
            response = self.scpi_socket.recv(65536)
            return response.decode('ascii')
        except socket.timeout:
            print("No data available."


class Logger:
    """
    bla
    """

    def __init__(self, host, scpi_port=5025):
        self.scpi_socket = SCPISocket(host, scpi_port)

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.disconnect()

    def connect(self):
        self.scpi_socket.connect()
        return self

    def disconnect(self):
        self.scpi_socket.disconnect()

    def config(self):
        commands = ["*RST\n",
            "configure:temperature tc,k,(@101)\n",
            "route:scan (@101)\n",
            "trigger:count 1",]
        command = ''.join(commands)
        self.scpi_socket.command(command)

    def start(self):
        self.scpi_socket.command("init")

    def get_data(self):
        return self.scpi_socket.command("fetch?")

    def display(self, text):
        self.scpi_socket.command("display:text '{}'".format(text))

    def reset_display(self):
        self.scpi_socket.command("display:text:clear")

