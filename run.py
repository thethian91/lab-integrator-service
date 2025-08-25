import asyncio
import os
import socket
import sys
from asyncio import Event
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml

from app.commons.hl7_engine import HL7Engine
from app.commons.logger import setup_logging
from app.helpers.router import FlowRouter
from app.services.orders_service import OrdersService
from app.services.results_service import ResultsService

app = typer.Typer(add_completion=False, help="Lab Integrator Service")


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def _guess_payload_format(payload: bytes) -> str:
    # Heurística rápida: HL7 suele iniciar con 'MSH'
    if payload.strip().startswith(b"MSH"):
        return "HL7"
    return "ASTM"


def _write_incoming(paths_cfg: dict, payload: bytes, fmt_hint: str | None = None) -> str:
    inbox = os.path.join(paths_cfg["inbox_root"], "finecare")
    _ensure_dir(inbox)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    fmt = fmt_hint or _guess_payload_format(payload)
    ext = "hl7" if fmt == "HL7" else "astm"
    fpath = os.path.join(inbox, f"{ts}.{ext}")
    with open(fpath, "wb") as f:
        f.write(payload)
    return fpath


# =============================


def resource_path(relative_path: str) -> str:
    """Devuelve la ruta absoluta a un recurso, ya sea ejecutando como .exe o en desarrollo"""
    if hasattr(sys, "_MEIPASS"):
        # Si es un ejecutable generado por PyInstaller
        base_path = sys._MEIPASS
    else:
        # Si es ejecución normal (dev)
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def load_cfg(path: str = "app/configs/settings.yaml"):
    config_path = resource_path(path)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.command()
def send_order(example: str = typer.Option("minimal", help="elige payload de ejemplo")):
    cfg = load_cfg()
    logger = setup_logging(cfg["paths"]["logs_root"], os.getenv("LOG_LEVEL", "INFO"))
    logger.log("INFO", "Iniciando envio de ordenes")
    engine = HL7Engine("template_reader_orm_hl7.yaml")
    router = FlowRouter(engine, cfg)
    svc = OrdersService(router, cfg["transport"], cfg["paths"], cfg["retry"])

    # Ejemplo estático: reemplaza por tu obtención real
    payload = {
        "paciente": {
            "tipo_doc": "CC",
            "num_doc": "123",
            "apellidos": "PEREZ",
            "nombres": "JUAN",
            "fecha_nac": "1990-01-01",
            "sexo": "M",
        },
        "atencion": {"servicio": "URGENCIAS"},
        "meta": {"fecha_mensaje": "2025-08-15 12:00:00", "msg_ctrl_id": "ABC123"},
        "ordenes": [
            {
                "orden_id": "O1",
                "placer_id": "P1",
                "codigo": "GLU",
                "descripcion": "GLUCOSA",
                "fecha_orden": "2025-08-15 12:00:00",
                "fecha_muestra": "2025-08-15 12:05:00",
            }
        ],
    }
    asyncio.run(svc.send_order(payload))


@app.command()
def results():
    cfg = load_cfg()
    logger = setup_logging(cfg["paths"]["logs_root"], os.getenv("LOG_LEVEL", "INFO"))
    logger.log("INFO", "Iniciando lectura de resultados pendientes por procesar")
    path_base = Path(cfg["paths"]["executable"])
    path_config = Path(cfg["paths"]["config"])
    path_template = Path(cfg["filename"]["template_hl7"])
    full_path = Path(f"{path_base}/{path_config}/{path_template}")
    engine = HL7Engine(f"{full_path}")
    router = FlowRouter(engine, cfg)
    svc = ResultsService(
        router, cfg["transport"], cfg["paths"], cfg["validation"]["strict_histogram_256"]
    )
    if cfg["transport"]["results"]["type"] == "file":
        glob_pat = cfg["transport"]["results"]["file"]["filename_glob"]
        asyncio.run(svc.run_file_mode(glob_pat))
    else:
        tcp = cfg["transport"]["results"]["tcp"]
        asyncio.run(svc.run_tcp_mode(tcp["host"], tcp["port"]))


@app.command()
# def run_results(stop_event: asyncio.Event | None = None):
def run_results(is_stop_event: bool = False):
    """
    Ejecuta una 'pasada' en modo FILE o arranca el loop TCP.
    - En FILE: procesa y retorna.
    - En TCP: se queda corriendo hasta que stop_event esté seteado
      (o hasta que run_tcp_mode termine).
    """
    stop_event: Optional[Event] = None
    cfg = load_cfg()
    logger = setup_logging(cfg["paths"]["logs_root"], os.getenv("LOG_LEVEL", "INFO"))
    logger.log("INFO", "Iniciando lectura de resultados pendientes por procesar")

    engine = HL7Engine(
        f"{cfg['paths']['executable']}{cfg['paths']['config']}/{cfg['filename']['template_hl7']}"
    )
    router = FlowRouter(engine, cfg)
    svc = ResultsService(
        router, cfg["transport"], cfg["paths"], cfg["validation"]["strict_histogram_256"]
    )

    async def _amain():
        if cfg["transport"]["results"]["type"] == "file":
            glob_pat = cfg["transport"]["results"]["file"]["filename_glob"]
            # Ideal: que run_file_mode acepte stop_event opcional (no bloqueante)
            try:
                await svc.run_file_mode(glob_pat, stop_event=stop_event)
            except TypeError:
                # Compat: si tu método no recibe stop_event
                # llama la versión vieja
                await svc.run_file_mode(glob_pat)
        else:
            tcp = cfg["transport"]["results"]["tcp"]
            # Ideal: que run_tcp_mode acepte stop_event opcional y revise periódicamente
            try:
                await svc.run_tcp_mode(tcp["host"], tcp["port"], stop_event=stop_event)
            except TypeError:
                # Compat: si no soporta stop_event, al menos ejecuta la versión actual
                await svc.run_tcp_mode(tcp["host"], tcp["port"])

    asyncio.run(_amain())


@app.command()
def finecare(
    host: str = typer.Option("0.0.0.0", help="IP local para escuchar"),
    port: int = typer.Option(8001, help="Puerto UDP (Finecare por defecto 8001)"),
    bufsize: int = typer.Option(65535, help="Tamaño buffer UDP"),
):
    """
    Receiver de resultados Finecare por UDP.
    - Guarda cada frame en /inbox_root/finecare/*.hl7|*.astm
    - Reusa el pipeline ResultsService para procesarlos
    """
    cfg = load_cfg()

    # host = cfg["transport"]["results"]["finecare"]["bind_ip"]
    # port = cfg["transport"]["results"]["finecare"]["port"]

    logger = setup_logging(cfg["paths"]["logs_root"], os.getenv("LOG_LEVEL", "INFO"))
    logger.log("INFO", f"Finecare UDP receiver escuchando en {host}:{port}")

    # Prepara motor/flujo (usa lo que ya tienes)
    engine = HL7Engine(
        f"[{cfg['paths']['executable']}{cfg['paths']['config']}/{cfg['filename']['template_hl7']}]"
    )
    router = FlowRouter(engine, cfg)
    svc = ResultsService(
        router, cfg["transport"], cfg["paths"], cfg["validation"]["strict_histogram_256"]
    )

    # Socket UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))

    while True:
        data, addr = sock.recvfrom(bufsize)
        logger.log("INFO", f"Datagrama recibido de {addr[0]}:{addr[1]} ({len(data)} bytes)")
        fpath = _write_incoming(cfg["paths"], data, None)

        try:
            # Delega a tu servicio actual de resultados
            svc.process_file(fpath)
            logger.log("INFO", f"Procesado OK: {fpath}")
        except Exception as e:
            logger.log("ERROR", f"Error procesando {fpath}: {e}")


if __name__ == "__main__":
    app()
