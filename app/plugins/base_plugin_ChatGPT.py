from abc import ABC, abstractmethod


class Listing:
    def __init__(self, title, price, location, url, score=0):
        self.title = title
        self.price = price
        self.location = location
        self.url = url
        self.score = score


class BasePlugin(ABC):

    name: str = "base"

    @abstractmethod
    def search(self, query: str) -> list[Listing]:
        """
        Return a list of Listing objects
        """
        pass
    