# BUILT-IN modules
import subprocess
import multiprocessing as mp
# MEDUSA modules
import constants
from tcp.async_tcp_server import TCPServer
# APP MODULES
from .app_constants import *


class AppController(TCPServer):
    """ Class that handles the communication between MEDUSA and Unity.

    The AppController must execute the Unity app and control the communication
    flow between MEDUSA and Unity by using a separate thread called
    ``AppControllerWorker``, which is initialized and started in the constructor
    of this class. The asynchronous communication is handled by a TCPServer
    instance, which is also initialized in the constructor. For this reason,
    this class must inherit from ``TCPServerReadInterface``, making mandatory
    the overriding of the following methods:
        - `on_data_received(messageReceived)` to receive messages.
        - `on_server_up()` to being notified that the server is ready.

    Attributes
    ----------
    app_settings : Settings
        Settings of this application (defined in `settings.py`).
    run_state : multiprocessing.Value
        State that controls the flow of MEDUSA.
    queue_to_controller : queue.Queue
        Queue used to receive messages in `AppControllerWorker`.
    queue_from_controller : queue.Queue
        Queue used to send messages from `AppControllerWorker`.
    tcp_server : TCPServer
        Asynchronous TCP server to receive and send parameters between MEDUSA
        and Unity.
    server_state : multiprocessing.Value
        State that controls the status of the TCP server app according to
        `constants.py`.
    unity_state : multiprocessing.Value
        State that controls the status of the Unity app according to
        `constants.py`.
    working_thread : AppControllerWorker
        Thread that controls the communication flow between MEDUSA and Unity.
    """

    def __init__(self, callback, app_settings, run_state):
        # Parameters
        self.TAG = '[apps.dev_app_unity.AppController]'
        self.callback = callback
        self.app_settings = app_settings
        self.run_state = run_state

        # Pass the IP and port to the TCPServer
        super().__init__(ip=self.app_settings.connection_settings.ip,
                         port=self.app_settings.connection_settings.port)

        # States
        self.server_state = mp.Value('i', SERVER_DOWN)
        self.unity_state = mp.Value('i', UNITY_DOWN)

    def closeEvent(self, event):
        self.close()
        event.accept()

    def start_application(self):
        """ Starts the Unity application that will act as a TCP client. """
        """ Starts the Unity application that will act as a TCP client.

                Uncomment subprocess.call and uncomment the other 2 lines to test the
                app in the Unity editor
                """
        subprocess.call([self.app_settings.connection_settings.path_to_exe,
                         self.app_settings.connection_settings.ip,
                         str(self.app_settings.connection_settings.port)])

    def start_server(self):
        """ Starts the TCP server in MEDUSA."""
        super().start()

    # --------------- SEND MESSAGES TO UNITY --------------- #        
    def send_parameters(self):
        print(self.TAG, "Setting parameters...")
        msg = dict()
        msg["event_type"] = "setParameters"
        msg["updates_per_min"] = self.app_settings.run_settings.updates_per_min
        self.send_command(msg)

    def play(self):
        print(self.TAG, "Play!")
        msg = dict()
        msg["event_type"] = "play"
        self.send_command(msg)

    def pause(self):
        print(self.TAG, "Pause!")
        msg = dict()
        msg["event_type"] = "pause"
        self.send_command(msg)

    def resume(self):
        print(self.TAG, "Resume!")
        msg = dict()
        msg["event_type"] = "resume"
        self.send_command(msg)

    def stop(self):
        print(self.TAG, "Stop!")
        msg = dict()
        msg["event_type"] = "stop"
        self.send_command(msg)

    def close(self):
        super().stop()
        self.server_state.value = SERVER_DOWN

    # --------------------- ABSTRACT METHODS -------------------- #
    def on_server_up(self):
        self.server_state.value = SERVER_UP
        print(self.TAG, "Server is UP!")
    
    def send_command(self, command_dict, client_addresses=None):
        """ Stores a dict command in the TCP server's buffer to send it in the
        next loop iteration.

        Parameters
        ----------
        command_dict : dict
            Dictionary that includes the command to be sent.
        client_addresses : list of (string, int)
            List of client's addresses who must receive the command, use None
            for sending the message to all connected clients.
        """
        super().send_command(client_addresses=client_addresses,
                             msg=command_dict)
        
    def on_data_received(self, client_address, received_message):
        """ Callback when TCP server receives a message from Unity.

        Parameters
        ----------
        client_address : (string, int)
            IP and port of the client that sent the message
        received_message : string
            JSON encoded string of the message received from the client,
            which will be decoded as a dictionary afterward.
        """
        client_address, msg = super().on_data_received(
            client_address, received_message)
        if msg["event_type"] == "waiting":
            # Unity is UP and waiting for the parameters
            self.unity_state.value = UNITY_UP
            print(self.TAG, "Unity app is opened.")
        elif msg["event_type"] == "ready":
            # Unity is READY to start
            self.unity_state.value = UNITY_READY
            self.run_state.value = constants.RUN_STATE_READY
            print(self.TAG, "Unity app is ready.")
        elif msg["event_type"] == "close":
            # Unity has closed the client
            self.unity_state.value = UNITY_FINISHED
            print(self.TAG, "Unity closed the client")
        elif msg["event_type"] == "request_samples":
            # Process the message using the App callback
            self.callback.process_event(msg)
        else:
            print(self.TAG, "Unknown message in 'on_data_received': " +
                  msg["event_type"])
