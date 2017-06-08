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

import socket
import queue
import threading
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

    def __init__(self, host, scpi_port=5025, timeout=2):
        self.host = host
        self.scpi_port = scpi_port
        self.timeout = timeout
        self.buffer = []
        self.scpi_socket = None
        self.io_threads = []
        self.out_queue = queue.Queue()
        self.in_queue = queue.Queue()
        self._stop_flag = False

    def connect(self):
        """
        Open a new scpi socket.

        Raises
        ------
        LoggerError :
            If the connection can not be established.
        """
        self._stop_flag = False
        self.scpi_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.scpi_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.scpi_socket.settimeout(self.timeout)
        try:
            self.scpi_socket.connect((self.host, self.scpi_port))
        except OSError:
            raise LoggerError("Could not connect to {} on scpi port {}.".format(
                self.host, self.scpi_port))
        targets = (self._input, self._output)
        for target in targets:
            thread = threading.Thread(target=target, args=(self._stop,))
            self.io_threads.append(thread)
            thread.start()

    def disconnect(self):
        """Close the connection to the scpi socket."""
        self._stop_flag = True
        for thread in self.io_threads:
            thread.join()
        self.io_threads.clear()
        self.scpi_socket.close()

    def _stop(self):
        return self._stop_flag

    def _output(self, stop):
        while not stop():
            try:
                cmd = self.out_queue.get(timeout=self.timeout)
            except queue.Empty:
                continue
            # for seq in "\r\n":
            #     cmd = cmd.replace(seq, "")
            cmd = cmd.encode('ascii') + b"\n"
            sent_bytes = 0
            while sent_bytes < len(cmd):
                sent = self.scpi_socket.send(cmd[sent_bytes:])
                if sent == 0:
                    raise LoggerError("SCPI Socket connection broken.")
                sent_bytes += sent

    def _input(self, stop):
        while not stop():
            try:
                data = self.scpi_socket.recv(65536)
                self.in_queue.put(data.decode('ascii'))
            except socket.timeout:
                continue

    def command(self, cmd, wait_for_respone=False):
        """
        Send a command to the logger.

        Parameters
        ----------
        com : string
            The command to be sent to the logger.

        Returns
        -------
        response : string
            The answer of the device.
        """
        self.out_queue.put(cmd)
        if wait_for_respone:
            try:
                answer = self.in_queue.get(timeout=self.timeout)
            except queue.Empty:
                raise ControllerError(
                    "No response to command '{}'. ".format(cmd) +
                    "I/O threads and logger still alive?")
            return answer


class Logger:
    """
    bla
    """

    def __init__(self, host, scpi_port=5025):
        self._scpi_socket = SCPISocket(host, scpi_port)

    def __enter__(self):
        return self.connect()

    def __exit__(self, *args):
        self.disconnect()

    def connect(self):
        self._scpi_socket.connect()
        return self

    def disconnect(self):
        self._scpi_socket.disconnect()

    def configure(self, channel):
        self._scpi_socket.command("*RST")
        self._scpi_socket.command("configure:temperature tc,k,(@{})".format(channel))
        self._scpi_socket.command("route:mon:chan (@{})".format(channel))
        self._scpi_socket.command("route:mon:stat on")

    def get_data(self):
        return self._scpi_socket.command("route:mon:data?", wait_for_respone=True)

    def reset_display(self):
        self._scpi_socket.command("display:text:clear")

    def display(self, text):
        self._scpi_socket.command("display:text '{}'".format(text))

