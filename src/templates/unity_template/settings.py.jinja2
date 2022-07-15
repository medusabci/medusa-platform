from medusa.components import SerializableComponent
import os


class Settings(SerializableComponent):
    def __init__(self, connection_settings = None, run_settings = None):
        self.connection_settings = connection_settings if \
            connection_settings is not None else ConnectionSettings()
        self.run_settings = run_settings if \
            run_settings is not None else RunSettings()


    def to_serializable_obj(self):
        sett_dict = {'connection_settings': self.connection_settings.__dict__,
                     'run_settings': self.run_settings.__dict__}
        return sett_dict

    @classmethod
    def from_serializable_obj(cls, dict_data):
        connection_settings = ConnectionSettings(**dict_data[
                                                 "connection_settings"])
        run_settings = RunSettings(**dict_data["run_settings"])

        return cls(connection_settings=connection_settings,
                   run_settings=run_settings)

class ConnectionSettings:
    def __init__(self, ip="127.0.0.1", port=50000, path_to_exe = None):

        self.ip = ip
        self.port = port
        self.path_to_exe = path_to_exe

        # Default .exe path
        if self.path_to_exe is None:
            self.path_to_exe = os.path.dirname(__file__) + \
                                '/unity/Unity app template.exe'

class RunSettings:
    def __init__(self, updates_per_min = 120):
        self.updates_per_min = updates_per_min