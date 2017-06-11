"""
Base classes that implement general I/O functionality with devices.
"""

import threading
import queue
from functools import wraps

# TODO add timeouts to signatures.

class ExceptionThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exception_queue = queue.Queue()
    
    def run(self):
        try:
            super().run()
        except BaseException as error:
            self.exception_queue.put(error)

    def join(self):
        super().join()
        try:
            exc = self.exception_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            raise exc
        

class IOBase():
    """
    The base class for all device related I/O.  Inherit from this class to get
    basic asynchronous I/O functionality with a thread and a queue for input
    and / or output.

    This class provides the methods `connect` and `disconnect` for the
    establishment and termination of the connection and a method `command` to
    send and receive data.

    `address` and `timeout` are stored as attributes and can be used by the
    other methods to connect to the device. `do_input` and `do_output` are
    Boolean flags that set if the class is used for input and / or output.
    """
    def __init__(self, address, timeout=2, do_input=True, do_output=True):
        self.address = address
        self.timeout = timeout
        self.threads = []
        self._targets = []
        if do_input:
            self.in_queue = queue.Queue()
            self._targets.append(self._input)
        if do_output:
            self.out_queue = queue.Queue()
            self._targets.append(self._output)
        self._stop = threading.Event()

    def _open(self):
        """
        Override this method to implement the initialzsation of the connection,
        e.g. connect to a socket / open a serial connection etc.
        """
        raise NotImplementedError

    def _close(self):
        """
        Override this method to implement the proper termination of the
        connection, e.g. close the socket / serial connection.
        """
        raise NotImplementedError

    def _send(self, cmd):
        """
        Override this method to implement outgoing data traffic, where `cmd``
        is the data to be sent.
        """
        raise NotImplementedError

    def _receive(self):
        """
        Override this method to implement the reception of incoming data.
        Return the data if data is available. Return `None` otherwise.
        """
        raise NotImplementedError

    def _output(self):
        """The main ouput thread."""
        while not self._stop.is_set():
            try:
                cmd = self.out_queue.get(timeout=self.timeout)
            except queue.Empty:
                continue
            self._send(cmd)
        while not self.out_queue.empty():
            self.out_queue.get_nowait()

    def _input(self):
        """The main input thread."""
        while not self._stop.is_set():
            data = self._receive()
            if data is not None:
                self.in_queue.put(data)
        while not self.in_queue.empty():
            self.in_queue.get_nowait()

    def connect(self):
        """Opens the connection to the device and starts all I/O threads."""
        self._stop.clear()
        self._open()
        for target in self._targets:
            name = self.__class__.__name__ + "." + target.__name__
            thread = ExceptionThread(target=target, name=name)
            print("Starting: {}".format(thread.name))
            self.threads.append(thread)
            thread.start()

    def disconnect(self):
        """Disconnects from the device and stops all I/O threads."""
        self._stop.set()
        for thread in self.threads:
            print("Joining: {}".format(thread.name))
            thread.join()
        self.threads.clear()
        self._close()

    def command(self, cmd, get_response=True, timeout=None):
        """
        Sends a command to the device and returns (optional) the response.

        Parameters
        ----------
        cmd :
            The command to be sent.
        get_response : Bool, optional
            If True, wait for a respone of the device.
        timeout: float, optional
            The maximal time in seconds that is waited for a response from the
            device. If timout is None, the timeout value of the class is used.

        Returns
        -------
        response : string
            The response of the device.

        Raises
        ------
        TimeoutError :
            If now response is received within self.timeout seconds.
        """
        if timeout is None:
            timeout = self.timeout
        if not self._stop.is_set():
            self.out_queue.put(cmd)
            if get_response:
                try:
                    answer = self.in_queue.get(timeout=timeout)
                except queue.Empty:
                    raise TimeoutError(
                        "No response to command '{}'. ".format(cmd) +
                        "I/O threads and device still alive?")
                return answer


class NotConnectedError(Exception):
    """Raised if a method of a device is called that is not connected yet."""


def on_connection(f):
    """
    Decorator for methods that are only allowed to be called if the
    connection is established.

    Raises
    ------
    NotConnectedError :
        If the device is not connected.
    """
    @wraps(f)
    def f_checked(self, *args, **kwargs):
        if self.connected:
            return f(self, *args, **kwargs)
        else:
            raise NotConnectedError(
                "'{}' can not be called if device".format(f.__name__) +
                " is not connected.")
    return f_checked


class Device():
    """
    Base class for devices that use one (ore more) of the IOBase classes as
    their basis for I/O.

    Provides context manager functionality for the secure termination of the
    connections and provides the mechanism for the decorator `_on_connection`
    to work. `_on_connection` prevents methods from being called if the
    connection is not established yet.
    """
    def __init__(self):
        self.connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    def _connect(self):
        """Override this method to implement the connection to the device."""
        raise NotImplementedError

    def _disconnect(self):
        """Override this method to implement the disconnection from the device."""
        raise NotImplementedError

    def connect(self):
        self.connected = True
        return self._connect()

    def disconnect(self):
        self.connected = False
        return self._disconnect()


