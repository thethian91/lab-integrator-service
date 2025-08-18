import os, yaml, asyncio
import typer
from app.commons.logger import setup_logging
from app.commons.hl7_engine import HL7Engine
from app.helpers.router import FlowRouter
from app.services.orders_service import OrdersService
from app.services.results_service import ResultsService

app = typer.Typer(add_completion=False)

def load_cfg():
    with open("app/configs/settings.yaml","r",encoding="utf-8") as f:
        return yaml.safe_load(f)

@app.command()
def send_order(example: str = typer.Option("minimal", help="elige payload de ejemplo")):
    cfg = load_cfg()
    logger = setup_logging(cfg["paths"]["logs_root"], os.getenv("LOG_LEVEL","INFO"))
    engine = HL7Engine("template_reader_orm_hl7.yaml")
    router = FlowRouter(engine, cfg)
    svc = OrdersService(router, cfg["transport"], cfg["paths"], cfg["retry"])

    # Ejemplo estático: reemplaza por tu obtención real
    payload = {
        "paciente": {"tipo_doc":"CC","num_doc":"123","apellidos":"PEREZ","nombres":"JUAN","fecha_nac":"1990-01-01","sexo":"M"},
        "atencion": {"servicio":"URGENCIAS"},
        "meta": {"fecha_mensaje":"2025-08-15 12:00:00","msg_ctrl_id":"ABC123"},
        "ordenes": [
            {"orden_id":"O1","placer_id":"P1","codigo":"GLU","descripcion":"GLUCOSA","fecha_orden":"2025-08-15 12:00:00","fecha_muestra":"2025-08-15 12:05:00"}
        ]
    }
    asyncio.run(svc.send_order(payload))

@app.command()
def results():
    cfg = load_cfg()
    logger = setup_logging(cfg["paths"]["logs_root"], os.getenv("LOG_LEVEL","INFO"))
    engine = HL7Engine(f"{cfg['paths']['executable']}{cfg['paths']['config']}/{cfg['filename']['template_hl7']}")
    router = FlowRouter(engine, cfg)
    svc = ResultsService(router, cfg["transport"], cfg["paths"], cfg['validation']['strict_histogram_256'])

    if cfg["transport"]["results"]["type"] == "file":
        glob_pat = cfg["transport"]["results"]["file"]["filename_glob"]
        asyncio.run(svc.run_file_mode(glob_pat))
    else:
        tcp = cfg["transport"]["results"]["tcp"]
        asyncio.run(svc.run_tcp_mode(tcp["host"], tcp["port"]))

if __name__ == "__main__":
    app()
