from pathlib import Path

from app.rag.watcher import _WatchHandler


class FakeService:
    def __init__(self) -> None:
        self.created: list[Path] = []
        self.modified: list[Path] = []
        self.deleted: list[Path] = []

    def handle_created(self, path: Path) -> None:
        self.created.append(path)

    def handle_modified(self, path: Path) -> None:
        self.modified.append(path)

    def handle_deleted(self, path: Path) -> None:
        self.deleted.append(path)


class FakeEvent:
    def __init__(self, src_path: str, is_directory: bool = False) -> None:
        self.src_path = src_path
        self.is_directory = is_directory


class FakeMoveEvent(FakeEvent):
    def __init__(self, src_path: str, dest_path: str, is_directory: bool = False) -> None:
        super().__init__(src_path, is_directory=is_directory)
        self.dest_path = dest_path


def test_watch_handler_forwards_file_events() -> None:
    service = FakeService()
    handler = _WatchHandler(service).instance

    handler.on_created(FakeEvent("D:/tmp/notes.md"))
    handler.on_modified(FakeEvent("D:/tmp/notes.md"))
    handler.on_deleted(FakeEvent("D:/tmp/notes.md"))

    assert service.created == [Path("D:/tmp/notes.md")]
    assert service.modified == [Path("D:/tmp/notes.md")]
    assert service.deleted == [Path("D:/tmp/notes.md")]


def test_watch_handler_translates_move_into_delete_and_create() -> None:
    service = FakeService()
    handler = _WatchHandler(service).instance

    handler.on_moved(FakeMoveEvent("D:/tmp/old.md", "D:/tmp/new.md"))

    assert service.deleted == [Path("D:/tmp/old.md")]
    assert service.created == [Path("D:/tmp/new.md")]
