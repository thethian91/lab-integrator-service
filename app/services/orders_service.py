import asyncio
from app.helpers.file_transport import FileSender
from app.helpers.tcp_transport import TcpSender
from app.commons.logger import logger

class OrdersService:
    def __init__(self, router, transport_cfg, paths, retry):
        self.router = router
        self.transport_cfg = transport_cfg
        self.paths = paths
        self.retry = retry

    async def send_order(self, payload: dict):
        hl7 = self.router.render_order(payload)
        self.router.archive_raw("sent", hl7, tag="order")

        if self.transport_cfg["orders"]["type"] == "file":
            sender = FileSender(self.paths["outbox"], self.transport_cfg["orders"]["file"]["filename_pattern"])
            p = sender.send(hl7)
            logger.info(f"Orden escrita en {p}")
        else:
            tcp = self.transport_cfg["orders"]["tcp"]
            sender = TcpSender(tcp["host"], tcp["port"], tcp.get("timeout_sec",5))
            attempts = self.retry["attempts"]; backoff = self.retry["backoff_sec"]
            for i in range(1, attempts+1):
                try:
                    await sender.send(hl7)
                    logger.info("Orden enviada por TCP")
                    break
                except Exception as ex:
                    logger.error(f"Intento {i}/{attempts} fallo: {ex}")
                    if i < attempts:
                        await asyncio.sleep(backoff)
                    else:
                        raise
