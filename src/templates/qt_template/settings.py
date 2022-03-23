from medusa.components import SerializableComponent


class Settings(SerializableComponent):

    def __init__(self, updates_per_min=60):
        self.updates_per_min = updates_per_min

    def to_serializable_obj(self):
        return self.__dict__

    @classmethod
    def from_serializable_obj(cls, dict_data):
        return cls(**dict_data)
