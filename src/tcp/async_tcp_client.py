""" Created on Tuesday March 23 19:00:43 2022
@author: Víctor Martínez-Cagigal
"""

import selectors
import socket
import sys
import threading
import traceback
import struct
import json
import io
from contextlib import closing
from abc import ABC, abstractmethod


class TCPClient(ABC):
    """ Represents an asynchronous TCP/IP client that provides real-time
    communication with an asynchronous TCP/IP server. Useful functions are:
    start(), stop() and send(). Check the example for a practical usage.
    Messages are sent using a customized header format, check the class
    TCPClientMessage if you need to know the details for e.g., implementing
    it using other language.

    Note
    ----------
    Implement the abstracts methods on_data_received() and send() to receive
    messages from server and send them to server, respectively, from a class
    that inherits from TCPClient.

    Parameters
    ----------
    ip : string
        Server IP (e.g., '127.0.0.1' for localhost).
    port: int
        Server port (e.g., 65432).

    Example
    --------
    Note: remove the decorators of @abstractmethod in on_data_received() and
    send() to execute this example.
    >>> from tcp.async_tcp_client import TCPClient
    >>> client = TCPClient('127.0.0.1', 65432)
    >>> client.start()
    >>> client.stop()
    """
    def __init__(self, ip, port):

        self.TAG = "[tcp/async_tcp_client/TCPClient]"
        self.ip = ip
        self.port = port

        # Other attributes
        self.selector = None
        self.socket = None
        self.message = None

        # Working loop
        self.must_stop_working_loop = True
        self.working_loop = None

    @staticmethod
    def is_socket_open(host, port):
        """ Checks if a socket is opened. In this class, the function is used
        to know if the server is already up.

        Parameters
        ----------
        host : string
            Socket IP.
        port: int
            Socket port.

        Returns
        ----------
        bool
            True if socket is opened, false otherwise.
        """
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            if sock.connect_ex((host, port)) == 0:
                return True
            else:
                return False

    def start(self):
        """ Starts the TCP/IP client asynchronously.

        First, provided the server is already up, the client starts a
        communication socket in nonblocking mode, connects to the server and
        registers the socket and the data type (i.e., TCPClientMessage) into
        the selector. Then, it starts a thread (TCPClient_WorkingLoopThread)
        that will listen for any reading or writing event.
        """
        # Check if the server is up
        if not self.is_socket_open(self.ip, self.port):
            print(self.TAG, 'ERROR: Cannot connect! It seems that the server '
                            'socket is not open yet')
            return

        # Open a TCP/IP socket
        print(self.TAG, '> Starting TCP/IP client...')
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Set the socket in non-blocking mode
        self.socket.setblocking(False)
        # Connect the client to the server
        self.socket.connect_ex((self.ip, self.port))
        # Register the socket in the selector (multiplexing)
        self.selector = selectors.DefaultSelector()
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.message = TCPClientMessage(self.selector,
                                        self.socket, (self.ip, self.port))
        self.selector.register(self.socket, events, data=self.message)
        print(self.TAG, '> Connected to %s:%s!' % (self.ip, self.port))

        # Start the listening working loop
        self.must_stop_working_loop = False
        self.working_loop = threading.Thread(target=self._working_loop, args=())
        self.working_loop.name = 'TCPClient_WorkingLoopThread'
        self.working_loop.start()

    def stop(self):
        """ Stops the TCP/IP client by unregistering the connection socket,
        closing the selector and the socket and joining the working listening
        thread.
        """
        # Stop working loop
        print(self.TAG, '> Closing signal received!')
        self.must_stop_working_loop = True

        # Closing selector
        try:
            self.selector.unregister(self.socket)
        except Exception:
            print(self.TAG, 'Error: selection.unregister() exception: %s' %
                  traceback.format_exc())
        self.selector.close()
        self.selector = None

        # Closing socket
        try:
            self.socket.close()
        except OSError:
            print(self.TAG, 'Error: socket.close() exception: %s' %
                  traceback.format_exc())
        finally:
            # Delete reference to socket object for garbage collection
            self.socket = None

        # Wait the working thread to end
        self.working_loop.join()
        print(self.TAG, '> Working loop thread joined')

        print(self.TAG, '> Client closed!')

    def _working_loop(self):
        """ This function is executed by the TCPClient_WorkingLoopThread to
        listen for new read or write events.

        Note that the processing of those events is made inside the message
        class. In case the TCPClient has received something from the server,
        on_data_received() function is called to pass the data to the
        abstract method so other class that inherit TCPClient can receive it.
        """
        try:
            print(self.TAG, '[thread] > Working loop started')
            while not self.must_stop_working_loop:
                events = self.selector.select(timeout=0)
                for key, mask in events:
                    message = key.data
                    rcv_msg = message.process_event(mask)
                    if rcv_msg:
                        self.on_data_received(rcv_msg)
                # Check for a socket being monitored to continue.
                if not self.selector.get_map():
                    break
        except (TCPServerDisconnected, ConnectionResetError):
            print(self.TAG, '[thread] > Server disconnected!')
        except Exception:
            print(self.TAG, '[thread] > Exception occurred: %s' %
                  traceback.format_exc())
        print(self.TAG, '[thread] > Working loop ended')
        return

    # ---------------------------- ABSTRACT METHODS ----------------------------
    @abstractmethod
    def send(self, msg):
        """ Method to send a message to the server.

        This abstract method must be implemented from any class that inherit
        from TCPClient.

        Parameter
        ---------
        msg : string or dict
            Message to be sent to the server. If it is a dict, then it is
            encoded in JSON format.
        """
        self.message.send(msg)

    @abstractmethod
    def on_data_received(self, received_msg):
        """ Method that is called whenever the TCPClient receives any message

        This abstract method must be implemented from any class that inherit
        from TCPClient.

        Returns
        ---------
        string
            Message received from the server
        """
        return received_msg


class TCPClientMessage:
    """ Represents a message from the TCPClient, containing all necessary
    functions to encode and decode all messages using a custom header.

    All messages are encoded following the next structure:
    .--------------------------------------------------------------------------.
    |                First header: proto-header with fixed length              |
    |                           Type: 2-byte integer                           |
    |                       Byte order: network (big-endian)                   |
    .--------------------------------------------------------------------------.
    .--------------------------------------------------------------------------.
    |                Second header: variable length JSON header                |
    |                           Type: Unicode text                             |
    |                             Encoding: UTF-8                              |
    |                   Length: specified by the first proto-header            |
    .--------------------------------------------------------------------------.
    .--------------------------------------------------------------------------.
    |                            Variable length content                       |
    |                      Type: specified in JSON header                      |
    |                    Encoding: specified in JSON header                    |
    |                   Length: specified in JSON header                       |
    .--------------------------------------------------------------------------.

    Parameters
    ----------
    selector: selectors.BaseSelector
        Selector in which this data type is registered.
    socket: socket
        Socket associated to this data type.
    address: tuple(string, int)
        Address (IP, port) of the socket.
    """
    def __init__(self, selector, socket, address):
        self.TAG = "[tcp/async_tcp_client/TCPClientMessage]"
        self.selector = selector
        self.socket = socket
        self.address = address
        self.server_ip, self.server_port = socket.getpeername()

        # Sending
        self._send_requests = list()
        self._send_buffer = b""

        # Reading
        self._recv_buffer = b""
        self._jsonheader_len = None  # Length of the JSON header
        self._jsonheader = None  # JSON header of the current message
        self._recv_message = None

    def process_event(self, mask):
        """ Processes both reading and writing events.

        Parameter
        ----------
        mask : int
            Selector mask (EVENT_READ or EVENT_WRITE).

        Returns
        ----------
        string or None
            Message received or None otherwise
        """
        if mask & selectors.EVENT_READ:
            received_msg = self.read()
            if received_msg is not None:
                return received_msg
        if mask & selectors.EVENT_WRITE:
            # Warning: if there is nothing to read(), the selector will only try
            # to write, that's why the send() function is used
            self._write()
        return None

    # -------------------------------- READING ---------------------------------
    def read(self):
        """ Main function to read any incoming message from the server.

        First, it reads a fixed number of bytes. If the first header,
        indicating the length of the subsequent header is included in those
        bytes, processes it. If the header length is already known,
        it processes the entire message header. If the header has already
        read, then it reads the message and starts again.

        Returns
        --------
        basestring
            Data read.
        """
        self._read_bytes()                      # Read some bytes
        if self._jsonheader_len is None:        # Process first header
            self._process_header()
        if self._jsonheader_len is not None:    # Process JSON header
            if self._jsonheader is None:
                self._process_jsonheader()
        if self._jsonheader:                    # Read the message
            data = self._process_message()
            if data is not None:
                self._jsonheader_len = None
                self._jsonheader = None
                self._recv_message = None
                return data

    def _read_bytes(self, no_bytes=4096):
        """ Reads a fixed number of bytes from the socket and store them into
        the buffer (self._recv_buffer).

        Parameters
        -------------
        no_bytes : int
            Max. number of bytes to read (default = 4096 bytes).
        """
        try:
            # Should be ready to read
            data = self.socket.recv(no_bytes)
        except BlockingIOError or ConnectionResetError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            print(self.TAG, '> Server (%s, %i) is temporarily unavailable' %
                  (self.server_ip, self.server_port))
            pass
        else:
            if data:
                # Stack the received message
                self._recv_buffer += data
            else:
                # Server disconnected!
                raise TCPServerDisconnected

    def _process_header(self):
        """ Processes the first header provided it is contained in the reading
        buffer.

        This header indicates the length of the next JSON header:
            - Length: 2 bytes
            - Type: 2 byte integer
            - Byte order: network (big-endian)
        """
        HEADER_LENGTH = 2
        if len(self._recv_buffer) >= HEADER_LENGTH:
            self._jsonheader_len = struct.unpack(
                ">H", self._recv_buffer[:HEADER_LENGTH]
            )[0]
            self._recv_buffer = self._recv_buffer[HEADER_LENGTH:]

    def _process_jsonheader(self):
        """ Processes the second header (the JSON header) if we already know its
        length.

        This header indicates the details of the JSON-encoded message that
        comes afterward. It must have the following items: "byteorder",
        "content-length", "content-type", and "content-encoding".
        """
        if len(self._recv_buffer) >= self._jsonheader_len:
            self._jsonheader = self._json_decode(
                self._recv_buffer[:self._jsonheader_len], "utf-8"
            )
            self._recv_buffer = self._recv_buffer[self._jsonheader_len:]
            # Assertion
            for required_header in ("byteorder", "content-length",
                                    "content-type", "content-encoding"):
                if required_header not in self._jsonheader:
                    raise ValueError(self.TAG,  "> Missing required JSON "
                                                "header: %s." % required_header)

    def _process_message(self):
        """ Reads the message as long as both first and second headers have been
        previously read.

        Returns
        ---------
        string or None
            None if message is not fully received, the read message otherwise.
        """
        content_length = self._jsonheader["content-length"]
        if not len(self._recv_buffer) >= content_length:
            # We don't have the entire message yet
            return None
        data = self._recv_buffer[:content_length]
        self._recv_buffer = self._recv_buffer[content_length:]
        if self._jsonheader["content-type"] == "text/json":
            encoding = self._jsonheader["content-encoding"]
            recv_message = self._json_decode(data, encoding)
        else:
            # Unknown content-type
            recv_message = data
        print(self.TAG, "> Received from server (%s, %i) [%s]: %s" %
              (self.server_ip, self.server_port, self._jsonheader[
                  "content-type"], recv_message))
        return recv_message

    # -------------------------------- WRITING ---------------------------------
    def send(self, content):
        """ Requests a message to be sent to the server.

        The message is not instantly sent, but it is appender to a list()
        buffer that will send the messages sequentially whenever the selector
        determines it is the time to write into the buffer.

        Parameter
        ------------
        content: string or dict()
            Content to be JSON-encoded and sent.
        """
        # Request something to send
        self._send_requests.append(content)
        print(self.TAG, '> Requested to send: %s' % content)

    def _write(self):
        """ Processes messages to be written.

        If there are requests, then takes one message request, encodes it
        using the custom headers and appends it to a sending buffer
        (self._send_buffer). Then, tries to write any binary-encoded message
        that it is inside the sending buffer.
        """
        # Append new messages to the buffer if requested
        if len(self._send_requests) > 0:
            # Take the first buffered request
            request = self._send_requests.pop(0)
            # Create the message with headers and append it to the buffer
            self._send_buffer += self._create_message(request)
        # Write the current buffer
        self._write_bytes()

    def _create_message(self, content, type="text/json", encoding="utf-8"):
        """ Encodes a request using our custom header-based message type.

        Parameters
        ------------
        content : string or dict()
            Request message to be sent.
        type : basestring
            Type of message (e.g., 'text/json')
        encoding : basestring
            Type of encoding (e.g., 'utf-8')

        Returns
        ------------
        binary string
            Encoded request.
        """
        # Encoding
        msg = content
        if type == "text/json":
            msg = self._json_encode(content, encoding)
        # Create headers
        jsonheader = {
            "byteorder": sys.byteorder,
            "content-type": type,
            "content-encoding": encoding,
            "content-length": len(msg),
        }
        jsonheader_bytes = self._json_encode(jsonheader, "utf-8")
        message_hdr = struct.pack(">H", len(jsonheader_bytes))
        message = message_hdr + jsonheader_bytes + msg
        return message

    def _write_bytes(self):
        """ Writes bytes into the socket if there is anything to be written.
        """
        if self._send_buffer:
            try:
                # Should be ready to write
                sent = self.socket.send(self._send_buffer)
            except BlockingIOError:
                # Resource temporarily unavailable (errno EWOULDBLOCK)
                print(self.TAG, '> Server (%s, %i) is temporarily unavailable' %
                      (self.server_ip, self.server_port))
                pass
            else:
                print(self.TAG, ' Sent to server (%s, %i): %s' %
                      (self.server_ip, self.server_port,
                       self._send_buffer[:sent]))
                self._send_buffer = self._send_buffer[sent:]

    # ------------------------------- UTILITIES --------------------------------
    def _json_encode(self, obj, encoding):
        """ Encodes any object using the desired encoding.

        Parameters
        ------------
        obj : object
            Any serializable object.
        encoding : basestring
            Type of encoding (e.g., 'utf-8')

        Returns
        --------
        binary string
            Encoded object in JSON format.
        """
        return json.dumps(obj, ensure_ascii=False).encode(encoding)

    def _json_decode(self, json_bytes, encoding):
        """ Decodes any JSON-encoded object using the desired encoding.

        Parameters
        ------------
        obj : object
            Any serializable object.
        encoding : basestring
            Type of encoding (e.g., 'utf-8')

        Returns
        --------
        object
            Decoded object.
        """
        tiow = io.TextIOWrapper(
            io.BytesIO(json_bytes), encoding=encoding, newline=""
        )
        obj = json.load(tiow)
        tiow.close()
        return obj


class TCPServerDisconnected(Exception):
    """ Custom exception to detect if the server has been disconnected. """
    pass


if __name__ == "__main__":
    pass
