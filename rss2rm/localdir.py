from pathlib import Path

from .uploader import Uploader


class LocalDirUploader(Uploader):
    def __init__(self, directory: str) -> None:
        self.directory = Path(directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)

    def upload(self, filename: str, data: bytes) -> bool:
        (self.directory / filename).write_bytes(data)
        return True
