from abc import ABC, abstractmethod


class BasePlugin(ABC):

    name = "base"

    @abstractmethod
    def search(self, query: str):
        pass
    