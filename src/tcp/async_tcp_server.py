""" Created on Tuesday March 23 19:00:42 2022
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
from abc import ABC, abstractmethod


class TCPServer(ABC):
    """ Represents an asynchronous TCP/IP server that provides real-time
    communication with multiple asynchronous TCP/IP clients. Useful functions
    are: start(), stop(), send_to() and send_to_all(). Check the example for a
    practical usage. Messages are sent using a customized header format,
    check the class TCPClientServer if you need to know the details for e.g.,
    implementing it using other language.

    Note
    ----------
    Implement the abstracts methods on_data_received() and send() to receive
    messages from clients and send them to clients, respectively, from a class
    that inherits from TCPServer.

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
    >>> from tcp.async_tcp_server import TCPServer
    >>> server = TCPServer('127.0.0.1', 65432)
    >>> server.start()
    >>> server.stop()
    """
    def __init__(self, ip, port):
        self.TAG = "[tcp/async_tcp_server/TCPServer]"
        self.ip = ip
        self.port = port

        # Other attributes
        self.selector = None
        self.socket = None
        self.clients = dict()

        # Working loop
        self.must_stop_working_loop = True
        self.working_loop = None

    def start(self):
        """ Starts the TCP/IP server asynchronously.

        First, the server creates a socket in the desired IP and port in
        nonblocking mode and enables it to listen for new connections. Then, it
        starts a thread (TCPServer_WorkingLoopThread) that will listen for
        any new client, or any reading or writing event.
        """
        # Open a TCP/IP socket to accept connections
        print(self.TAG, '> Opening TCP/IP server at %s:%s...' % (self.ip, self.port))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Avoid bind() exception: OSError: [Errno 48] Address already in use
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Associate the socket with the IP and port
        self.socket.bind((self.ip, self.port))

        # Enable the server to accept connections
        print(self.TAG, '> Accepting connections in non-blocking mode...')
        self.socket.listen()
        # Set the socket in non-blocking mode
        self.socket.setblocking(False)
        # Register the listening (connections) socket in the selector (multiplexing)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.socket, selectors.EVENT_READ, data=None)
        # Start the infinite working loop in a separate thread
        self.must_stop_working_loop = False
        self.working_loop = threading.Thread(target=self._working_loop, args=())
        self.working_loop.name = 'TCPServer_WorkingLoopThread'
        self.working_loop.start()
        # Notify that the server is up
        self.on_server_up()

    def stop(self):
        """ Stops the TCP/IP server by closing all the sockets created for
        each client, joining the working thread and closing the selector.
        """
        print(self.TAG, '> Closing signal received!')

        # Close working thread
        self.must_stop_working_loop = True
        self.working_loop.join()
        print(self.TAG, '> Working loop thread closed')

        # Close selector
        self.selector.close()

        # Close clients
        for address in self.clients:
            self.clients[address]['socket'].close()
        self.clients = dict()

        # Restart everything
        self.selector = None
        self.socket = None
        print(self.TAG, '> Server closed!')

    def _working_loop(self):
        """ This function is executed by the TCPServer_WorkingLoopThread to
        listen for new connections and read or write events. A selector that
        acts as a multiplexer detects, for each CPU cycle, if there are write
        or read events associated to each client.

        Note that the processing of those events is made inside the message
        class. In case the TCPServer has received something from a client, the
        on_data_received() function is called to pass the data to the
        abstract method so other class that inherit TCPServer can receive it.
        """
        try:
            print(self.TAG, '[thread] > Working loop started')
            while not self.must_stop_working_loop:
                events = self.selector.select(timeout=0)
                for key, mask in events:
                    if key.data is None:
                        # New connection
                        self._handle_new_client()
                    else:
                        # It must be a write or read event
                        message = key.data
                        try:
                            rcv_msg = message.process_event(mask)
                            if rcv_msg:
                                self.on_data_received(message.address, rcv_msg)
                        except TCPClientDisconnected:
                            # If client disconnected, close it but keep
                            # monitoring the rest of them
                            self._close_client(message.client_ip + ':' +
                                               str(message.client_port))
                            pass
        except Exception:
            print(self.TAG, '[thread] > Exception occurred')
            print(traceback.format_exc())
        finally:
            print(self.TAG, '[thread] > Working loop ended')

    def _handle_new_client(self):
        """ Handles a new client connection to the server.

        If the _working_loop() receives an empty message that it is not an
        instance of the TCPServerMessage class, then it is recognised as a
        new connection. In that case, _handle_new_client() is called to
        accept that input connection by: (1) accepting that socket connection
        (each client has a unique socket), (2) setting that socket connection in
        nonblocking mode (asynchronous calls), (3) creating a
        TCPServerMessage type class to receive and send messages to the
        client, (4) registering the socket and the message class into the
        selector so it can be multiplexed (read and write events can be
        detected), and (5) storing the info of the client into the dictionary
        self.clients() to have points to the socket and the message type.
        """
        # Accept input connection (should be ready to read)
        client_socket, client_connection = self.socket.accept()
        client_socket.setblocking(False)
        client_ip, client_port = client_connection
        print(self.TAG, '> Accepted new client from %s:%s!' %
              (client_ip, client_port))

        # Create the message type
        data = TCPServerMessage(self.selector, client_socket, client_connection)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE

        # Register the client socket and its message class into the multiplexer
        self.selector.register(client_socket, events, data=data)

        # Store the info
        str_client_conn = client_ip + ':' + str(client_port)
        self.clients[str_client_conn] = {'socket': client_socket, 'connection': client_connection, 'data': data}

    def _close_client(self, client_address):
        """ Closes the connection to a client.

        A connection is closed by (1) unregistering the socket from the
        selector (multiplexer) so it is not considered anymore in the
        _working_loop(), (2) closing the client socket, and (3) deleting
        client info from the self.clients dictionary.

        Parameters
        -----------
        client_address : basestring
            Client address in the form of IP:port (e.g., '127.0.0.1:65432')
        """
        ip, port = client_address.split(':')
        port = int(port)
        print(self.TAG, '> Client (%s, %i) closed the connection' % (
            ip, int(port)))
        self.selector.unregister(self.clients[client_address]['socket'])
        self.clients[client_address]['socket'].close()
        self.clients.pop(client_address, None)

    def _send_to_all(self, msg):
        """ Send a message to all clients at once.

        Parameter
        ---------
        msg : string or dict
            Message to be sent. If it is a dict, then it is encoded in JSON
            format.
        """
        for ip in self.clients:
            self.clients[ip]['data'].send(msg)

    def _send_to(self, client_address, msg):
        """ Send a message to a specific client.

        Parameter
        ---------
        client_address : basestring
            Client address in the form of IP:port (e.g., '127.0.0.1:65432')
        msg : string or dict
            Message to be sent. If it is a dict, then it is encoded in JSON
            format.
        """
        if client_address in self.clients:
            self.clients[client_address]['data'].send(msg)
        else:
            print(self.TAG, '> Unknown client %s' % client_address)

    # ---------------------------- ABSTRACT METHODS ----------------------------
    @abstractmethod
    def send_command(self, client_addresses, msg):
        """ Method to send a message to one or more clients.

        This abstract method must be implemented from any class that inherit
        from TCPServer.

        Parameter
        ---------
        client_addresses: list of (string, int)
            List of client addresses (IP, port). Use None to send data to all
            clients.
        msg : string or dict
            Message to be sent to the client. If it is a dict, then it is
            encoded in JSON format.
        """
        if client_addresses is None:
            self._send_to_all(msg)
            return
        for client_address in client_addresses:
            add_ = client_address[0] + ':' + client_address[1]
            self._send_to(add_, msg)

    @abstractmethod
    def on_data_received(self, client_address, received_msg):
        """ Method that is called whenever the TCPServer receives any message

        This abstract method must be implemented from any class that inherit
        from TCPServer.

        Returns
        ---------
        (string, int), string
            Client address (IP, port) and message received from that client.
        """
        return client_address, received_msg

    @abstractmethod
    def on_server_up(self):
        """ Method that is called whenever the TCPServer has been started.

        This abstract method must be implemented from any class that inherit
        from TCPServer.
        """
        pass


class TCPServerMessage:
    """ Represents a message from the TCPServer, containing all necessary
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
        Client socket associated to this data type.
    address: tuple(string, int)
        Address (IP, port) of the socket.
    """
    def __init__(self, selector, socket, address):
        self.TAG = "[tcp/async_tcp_server/TCPServerMessage]"
        self.selector = selector
        self.socket = socket
        self.address = address
        self.client_ip, self.client_port = socket.getpeername()

        # Sending
        self._send_requests = list()
        self._send_buffer = b""

        # Reading
        self._recv_buffer = b""
        self._jsonheader_len = None     # Length of the JSON header
        self._jsonheader = None         # JSON header of the current message
        self._recv_message = None

    def process_event(self, mask):
        """ Processes both reading and writing events.

        Parameter
        ----------
        mask : int
            Selector mask (EVENT_READ or EVENT_WRITE).
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
        """ Main function to read any incoming message from a client.

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
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            print(self.TAG, '> Client (%s, %i) is temporarily unavailable' %
                  (self.client_ip, self.client_port))
            pass
        else:
            if data:
                # Stack the received message
                self._recv_buffer += data
            else:
                # Client disconnected!
                raise TCPClientDisconnected

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
        print(self.TAG, "> Received from (%s, %i) [%s]: %s" %
              (self.client_ip, self.client_port, self._jsonheader[
                  "content-type"], recv_message))
        return recv_message

    # -------------------------------- WRITING ---------------------------------
    def send(self, content):
        """ Requests a message to be sent to the client associated with this
        class.

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
                print(self.TAG, '> Client (%s, %i) is temporarily unavailable' %
                      (self.client_ip, self.client_port))
                pass
            else:
                print(self.TAG, ' Sent to client (%s, %i): %s' %
                      (self.client_ip, self.client_port,
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


class TCPClientDisconnected(Exception):
    """ Custom exception to detect if a client has been disconnected. """
    pass


if __name__ == "__main__":
    pass
