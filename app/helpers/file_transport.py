import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer


class FileSender:
    def __init__(self, outbox: str, pattern: str):
        self.outbox = Path(outbox)
        self.outbox.mkdir(parents=True, exist_ok=True)
        self.pattern = pattern

    def send(self, hl7_text: str) -> str:
        fname = self.pattern.format(
            timestamp=datetime.now().strftime("%Y%m%d%H%M%S"), uuid=uuid.uuid4().hex[:8]
        )
        p = self.outbox / fname
        p.write_text(hl7_text, encoding="utf-8")
        return str(p)


# Watchdog consumer para resultados por carpeta
"""
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
import asyncio, time

class FileWatcher:
    def __init__(self, inbox: str, glob: str, on_message_async, loop: asyncio.AbstractEventLoop):
        self.inbox = Path(inbox); self.inbox.mkdir(parents=True, exist_ok=True)
        self.loop = loop
        self.on_message_async = on_message_async

        self.handler = PatternMatchingEventHandler(patterns=[glob], ignore_directories=True)

        def _submit(path: Path):
            # pequeña espera (debounce) por archivos que aún se están escribiendo
            for _ in range(10):
                try:
                    text = path.read_text(encoding="utf-8")
                    break
                except Exception:
                    time.sleep(0.05)
            else:
                text = path.read_text(encoding="utf-8")
            asyncio.run_coroutine_threadsafe(self.on_message_async(text, str(path)), self.loop)

        self.handler.on_created = lambda e: _submit(Path(e.src_path))
        self.handler.on_modified = lambda e: _submit(Path(e.src_path))
        self.handler.on_moved = lambda e: _submit(Path(e.dest_path))

        self.observer = Observer()

    def start(self):
        self.observer.schedule(self.handler, str(self.inbox), recursive=False)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()
"""


class FileWatcher:
    def __init__(self, inbox: str, glob: str, on_message_async, loop: asyncio.AbstractEventLoop):
        self.inbox = Path(inbox)
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.loop = loop
        self.on_message_async = on_message_async
        self.handler = PatternMatchingEventHandler(patterns=[glob], ignore_directories=True)

        def _submit(path: Path):
            # Si el archivo ya no existe, no hay nada que leer (pudo haberse movido)
            if not path.exists():
                return
            # Espera breve hasta que termine de escribirse
            for _ in range(10):
                try:
                    text = path.read_text(encoding="utf-8")
                    break
                except FileNotFoundError:
                    # Se movió justo ahora: abortar silenciosamente
                    return
                except Exception:
                    time.sleep(0.05)
            else:
                # Último intento; si vuelve a fallar, deja que explote para que lo veas en logs
                text = path.read_text(encoding="utf-8")

            # Ejecutar la corrutina en el loop principal (thread-safe)
            asyncio.run_coroutine_threadsafe(self.on_message_async(text, str(path)), self.loop)

        # Usa src en created, dest en moved; y en modified valida que exista
        self.handler.on_created = lambda e: _submit(Path(e.src_path))
        self.handler.on_modified = lambda e: _submit(Path(e.src_path))
        self.handler.on_moved = lambda e: _submit(Path(e.dest_path))

        self.observer = Observer()

    def start(self):
        self.observer.schedule(self.handler, str(self.inbox), recursive=False)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()
