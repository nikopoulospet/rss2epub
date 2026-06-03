from abc import ABC, abstractmethod


class Uploader(ABC):
    @abstractmethod
    def upload(self, filename: str, data: bytes) -> bool:
        """Upload data as filename. Returns True on success."""
