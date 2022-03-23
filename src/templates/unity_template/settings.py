from medusa.components import SerializableComponent
import os


class Settings(SerializableComponent):

    def __init__(self, updates_per_min=120, path_to_exe=None, ip="127.0.0.1",
                 port=50000):
        self.path_to_exe = path_to_exe
        self.ip = ip
        self.port = port

        self.updates_per_min = updates_per_min  # How many updates per min
                                                # will Unity request?

        # Default .exe path
        if self.path_to_exe is None:
            self.path_to_exe = os.path.join(
                os.getcwd(), 'apps/dev_app_unity/unity/dev_app_unity.exe')

    def to_serializable_obj(self):
        return self.__dict__

    @classmethod
    def from_serializable_obj(cls, dict_data):
        return cls(**dict_data)
