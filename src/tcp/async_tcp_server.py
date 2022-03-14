import asyncio, constants, threading, json, time
from abc import ABC, abstractmethod

END_OF_MESSAGE = b"#_?END?_#"


class TCPServer(ABC):
    """ This class represents an asynchronous TCP server using asyncio.

        Example of use:
            tcpserver = TCPServer('127.0.0.1', 8888)
            asyncio.run(tcpserver.start())
    """

    def __init__(self, ip, port, magic_message=END_OF_MESSAGE):
        """ Constructor that takes the IP and port that will run the server.

            :param ip:      (str) server's IP.
            :param port:    (int) server's port.
        """
        self.TAG = "[tcp/async_tcp_server/TCPServer]"
        self.ip = ip
        self.port = port

        self.END_OF_MESSAGE = magic_message
        self.server = None
        self.clients = []
        self.mustClose = False
        self.background_thread = None
        self.loop = None
        self.tasks_pending = None

    async def start(self):
        """ This method initializes the server. DO NOT CALL this method,
        use self.start_on_thread instead. """
        self.server = await asyncio.start_server(self.handle_client, self.ip, self.port)
        print("Serving on " + str(self.ip) + ":" + str(self.port) + "...")
        self.on_server_up()

        async with self.server:
            await self.server.serve_forever()

    def loop_in_thread(self, loop):
        """ This method sets the background thread event loop. """
        asyncio.set_event_loop(self.loop)
        try:
            __, self.tasks_pending, _ = self.loop.run_until_complete(self.start())
        except asyncio.exceptions.CancelledError:
            if self.tasks_pending is not None:
                for task in self.tasks_pending:
                    task.close()
            print(self.TAG, 'Listening cancelled')

    async def start_on_thread(self):
        """ This method initializes the server on a background thread. """
        print("Serving in background thread on " + str(self.ip) + ":" + str(self.port) + "...")
        self.loop = asyncio.new_event_loop()
        self.background_thread = threading.Thread(target=self.loop_in_thread, args=(self.loop,))
        self.background_thread.start()

    async def handle_client(self, reader, writer):
        # Add the client
        client = {'id': len(self.clients), 'reader': reader, 'writer': writer}
        self.clients.append(client)
        print(self.TAG, 'Client added! No clients: ' + str(len(self.clients)))

        # Create the asynchronous task to read from this client
        while not self.mustClose:
            try:
                msg = await self.read_data_from_client(client)
                if msg == "close":
                    self.mustClose = True
            except asyncio.exceptions.IncompleteReadError:
                print(self.TAG, "Listening thread cancelled")
                break

        # Close this client
        print(self.TAG, "Closing client #" + str(client['id']) + " connection.")
        client["writer"].close()
        self.clients.pop(client['id'])

    async def read_data_from_client(self, client):
        data = await client["reader"].readuntil(self.END_OF_MESSAGE)
        addr = client["writer"].get_extra_info('peername')
        message = data.decode()[:-len(self.END_OF_MESSAGE)]
        print(f"{addr!r} said: " + message)
        # Send the message to the callback class
        self.on_data_received(message)
        return message

    def write_data_to_client(self, client, message):
        data = message.encode("ascii") + self.END_OF_MESSAGE
        addr = client["writer"].get_extra_info('peername')
        client["writer"].write(data)
        print(self.TAG, f"Sent to {addr!r}: " + message)

    def get_client(self, idx):
        return self.clients[idx]

    def close(self):
        self.mustClose = True
        if self.loop:
            print(self.TAG, 'Closing pending tasks...')
            for task in asyncio.all_tasks(self.loop):
                task.cancel()
        print(self.TAG, 'Waiting listening thread to be closed...')
        self.background_thread.join()
        print(self.TAG, 'Closing server...')
        self.server.close()
        print(self.TAG, 'AsyncTCPServer is closed.')

    # --------------------- ABSTRACT METHODS -------------------- #

    @abstractmethod
    def on_data_received(self, received_message):
        return json.loads(received_message)

    @abstractmethod
    def on_server_up(self):
        pass

    @abstractmethod
    def send_command(self, command_dict, client_idx=0):
        client = self.get_client(client_idx)
        self.write_data_to_client(client, json.dumps(command_dict))