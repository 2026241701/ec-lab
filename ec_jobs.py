"""Qt worker without importing spreadsheet or numerical processing libraries."""
from PySide6.QtCore import QObject, Signal, Slot


class Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, job):
        super().__init__()
        self.job = job

    @Slot()
    def run(self):
        try:
            result = self.job(self.progress.emit)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)
