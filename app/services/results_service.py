# app/services/results_service.py
import asyncio
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Union

from pydantic import ValidationError

from app.commons.logger import logger
from app.helpers.file_transport import FileWatcher
from app.helpers.tcp_transport import TcpServer
from app.validation.validators import validate_hl7_message_or_raise


def generate_inbox_filename(
    source: Union[tuple[str, int], str],
    analyzer: str = "unknown",
    origin: str = "auto",  # tcp | file | udp | manual | auto
    extension: str = "json",
) -> str:
    """
    Genera nombre de archivo para inbox, con timestamp y origen.
    Ej:
    - TCP:   20250821-170605-123456_icon_tcp_192_168_1_45_5002.json
    - FILE:  20250821-170605-123456_finecare_file_imported.json
    """

    if not isinstance(source, (tuple, str)):
        raise TypeError(
            f"Invalid type for source: expected tuple or str, got {type(source).__name__}"
        )

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")  # Para orden natural
    if isinstance(source, tuple):
        ip, port = source
        ip_safe = re.sub(r"\W", "_", ip)
        source_str = f"{origin}_{ip_safe}_{port}"
    else:
        # Usar solo el nombre base si es un path
        base_name = os.path.basename(source)
        base_name = os.path.splitext(base_name)[0]  # sin extensión
        safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", base_name)
        source_str = f"{origin}_{safe_base}"
    filename = f"{ts}_{analyzer}_{source_str}.{extension}"
    return filename


class ResultsService:
    def __init__(self, router, transport_cfg, paths, strict_histogram_256: bool = True):
        self.router = router
        self.transport_cfg = transport_cfg
        self.paths = paths
        self.strict_histogram_256 = strict_histogram_256
        Path(paths["archive"]).mkdir(parents=True, exist_ok=True)
        Path(paths["error"]).mkdir(parents=True, exist_ok=True)

    async def _process_text(self, hl7_text: str, src: str):
        # 1) archiva crudo siempre
        self.router.archive_raw("recv", hl7_text, tag="result")
        try:
            # 2) valida (MSH-9 requerido y histogramas de 256 bytes)
            validate_hl7_message_or_raise(hl7_text)
            # 3) extrae y escribe JSON
            # data = self.router.extract_results(hl7_text)
            data = self.router.transform_hl7_result(hl7_text)
            filename = generate_inbox_filename(src, origin="file" if src else "tcp")
            out_json = Path(self.paths["archive"]) / f"{filename}"
            out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Resultado procesado y archivado: {out_json}")

            # 4) mueve el HL7 procesado a archive/hl7/
            if src and Path(src).exists():
                dst_dir = Path(self.paths["archive"]) / "hl7"
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(src, dst_dir / Path(src).name)

        except ValidationError as ve:
            if self.strict_histogram_256:
                # → Este archivo está mal: llévalo a error/ y NO tumbar el servicio
                err_name = Path(src).name if src else "tcp_result.err.hl7"
                errp = Path(self.paths["error"]) / err_name
                errp.write_text(hl7_text, encoding="utf-8")
                logger.error(f"Validación falló para {err_name}: {ve}")
                return  # early exit

            # → Este archivo está mal: llévalo a error/ y NO tumbar el servicio
            err_name = Path(src).name if src else "tcp_result.err.hl7"
            errp = Path(self.paths["error"]) / err_name
            errp.write_text(hl7_text, encoding="utf-8")
            logger.error(f"Validación falló para {err_name}: {ve}")
            return  # early exit
        except Exception as ex:
            # Otros errores de parseo/extracción también van a error/
            err_name = Path(src).name if src else "tcp_result.err.hl7"
            errp = Path(self.paths["error"]) / err_name
            errp.write_text(hl7_text, encoding="utf-8")
            logger.exception(f"Error procesando resultado: {ex}. Movido a {errp}")
            return

    async def _process_backlog(self, glob_pat: str):
        inbox = Path(self.paths["inbox"])
        files = sorted(inbox.glob(glob_pat))
        if not files:
            return
        logger.info(f"Backlog detectado: {len(files)} archivo(s) en {inbox}")
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"No se pudo leer {f}: {e}; reintento breve...")
                await asyncio.sleep(0.1)
                text = f.read_text(encoding="utf-8")
            # Asegura que un fallo no detenga el backlog completo
            try:
                await self._process_text(text, str(f))
            except Exception as ex:
                logger.exception(f"Fallo inesperado con {f}: {ex}")

    async def run_file_mode(self, glob_pat: str):
        loop = asyncio.get_running_loop()

        # 1) Procesar backlog existente
        await self._process_backlog(glob_pat)

        # 2) Arrancar watcher para nuevos archivos
        watcher = FileWatcher(self.paths["inbox"], glob_pat, self._process_text, loop)
        watcher.start()
        logger.info("Escuchando carpeta de resultados...")
        try:
            await asyncio.Event().wait()
        finally:
            watcher.stop()

    async def run_tcp_mode(self, host: str, port: int):
        server = TcpServer(host, port, lambda txt, peer: self._process_text(txt, f"tcp_{peer}"))
        logger.info(f"Servidor TCP resultados en {host}:{port}")
        await server.start()
