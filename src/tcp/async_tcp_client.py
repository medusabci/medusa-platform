import asyncio, constants


class TCPClient:
    """ This class represents an asynchronous TCP client using asyncio.

        Example of use:
            client = TCPClient('127.0.0.1', 8888)
            asyncio.run(client.start())
    """

    def __init__(self, ip, port):
        """ Constructor that takes the IP and port of the server to connect to.

            :param ip:      (str) server's IP.
            :param port:    (int) server's port.
        """
        self.ip = ip
        self.port = port

        self.END_OF_MESSAGE = constants.END_OF_MESSAGE
        self.mustClose = False
        self.reader = None
        self.writer = None

    async def start(self):
        """ This method initializes the connection and queues a listener in the event loop."""
        try:
            # Start the connection
            self.reader, self.writer = await asyncio.open_connection(self.ip, self.port)
            print("Connected to " + str(self.ip) + ":" + str(self.port) + "...")
            self.isConnected = True

            # Read until the socket is closed
            while not self.mustClose:
                msg = await self.read_data_from_server()
                if msg == "close":
                    self.close()

            # Disconnect
            print("Client disconnected.")
            self.writer.close()
            self.isConnected = False
        except Exception as e:
            self.close()
            print(e)

    async def read_data_from_server(self):
        """ This method reads data from server. """
        data = await self.reader.readuntil(self.END_OF_MESSAGE)
        addr = self.writer.get_extra_info('peername')
        message = data.decode()[:-len(self.END_OF_MESSAGE)]
        print(f"Server said {addr!r}: " + message)
        return message

    def write_data_to_server(self, message):
        """ This method writes a message to the server.

            :param message:     (str) message to send.
        """
        data = message.encode("ascii") + self.END_OF_MESSAGE
        addr = self.writer.get_extra_info('peername')
        self.writer.write(data)
        #await self.writer.drain()
        print(f"Sent to server {addr!r}: " + message)

    def close(self):
        """ This function sets the close status to true. The event loop will detect it and close the connection. """
        self.mustClose = True