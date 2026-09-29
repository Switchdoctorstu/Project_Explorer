from __future__ import annotations

from pathlib import Path

from .errors import ProjectLoadError
from .jvm import JvmSession


class MpxjSession:
    def __init__(self, jar_path: Path):
        self.jvm = JvmSession(jar_path)

    @property
    def java_version(self) -> str:
        return self.jvm.java_version

    def start(self) -> None:
        self.jvm.start()

    def read_project(self, filename: str):
        project = self.jvm.read(filename)
        if project is None:
            raise ProjectLoadError("MPXJ did not return a project for the selected file.")
        return project

    def shutdown(self) -> None:
        self.jvm.shutdown()
