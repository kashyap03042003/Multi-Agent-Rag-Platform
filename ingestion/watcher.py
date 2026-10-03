import logging
import time
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from config.settings import settings
from ingestion.events import get_redis, publish
from ingestion.loader import is_supported

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("watcher")


class DataDirHandler(FileSystemEventHandler):
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.redis = get_redis()

    def emit(self, path: str, action: str) -> None:
        rel = Path(path).resolve().relative_to(self.root)
        if is_supported(rel):
            publish(self.redis, str(rel), action)
            logger.info("Published %s %s", action, rel)

    def on_created(self, event):
        if not event.is_directory:
            self.emit(event.src_path, "upsert")

    def on_modified(self, event):
        if not event.is_directory:
            self.emit(event.src_path, "upsert")

    def on_deleted(self, event):
        if not event.is_directory:
            self.emit(event.src_path, "delete")

    def on_moved(self, event):
        if not event.is_directory:
            self.emit(event.src_path, "delete")
            self.emit(event.dest_path, "upsert")


def main():
    root = Path(settings.data_dir)
    observer = Observer()
    observer.schedule(DataDirHandler(root), str(root), recursive=True)
    observer.start()
    logger.info("Watching %s", root.resolve())
    try:
        while True:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
