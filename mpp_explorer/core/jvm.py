from __future__ import annotations

from pathlib import Path

import jpype


class JvmSession:
    def __init__(self, jar_path: Path):
        self.jar_path = Path(jar_path)
        self.reader_class = None
        self.java_version = ""

    def start(self) -> None:
        if not self.jar_path.exists():
            raise FileNotFoundError(
                f"Cannot find {self.jar_path.name}.\nExpected location:\n{self.jar_path}"
            )

        if not jpype.isJVMStarted():
            jpype.startJVM(classpath=[str(self.jar_path)])

        self.reader_class = jpype.JClass("net.sf.mpxj.reader.UniversalProjectReader")
        system_class = jpype.JClass("java.lang.System")
        self.java_version = str(system_class.getProperty("java.version"))

    def is_ready(self) -> bool:
        return self.reader_class is not None

    def read(self, filename: str):
        if self.reader_class is None:
            raise RuntimeError("MPXJ reader is not initialised.")
        reader = self.reader_class()
        return reader.read(str(filename))

    def shutdown(self) -> None:
        try:
            if jpype.isJVMStarted():
                jpype.shutdownJVM()
        except Exception:
            pass


def jclass(name: str):
    return jpype.JClass(name)
