import asyncio

VT = b'\x0b'  # <VT>
FS = b'\x1c'  # <FS>
CR = b'\x0d'  # <CR>

async def read_mllp_messages(reader: asyncio.StreamReader):
    """
    Lee un stream MLLP y produce mensajes HL7 (str) delimitados por VT ... FS CR.
    Permite múltiples mensajes en una sola conexión.
    """
    buf = bytearray()
    while True:
        chunk = await reader.read(4096)
        if not chunk:
            break
        buf.extend(chunk)
        while True:
            # Busca VT
            try:
                start = buf.index(VT)
            except ValueError:
                # Si no hay VT, descarta basura anterior y sigue leyendo
                buf.clear()
                break
            # Busca FS CR después de start
            try:
                fs = buf.index(FS, start + 1)
                if fs + 1 >= len(buf):
                    # Falta CR y/o datos -> leer más
                    break
                if buf[fs + 1] != CR[0]:
                    # No hay CR después de FS -> espera más
                    break
                # Extraer mensaje entre VT y FS
                payload = bytes(buf[start + 1: fs])  # sin VT/FS/CR
                # Consumir hasta CR (fs+2)
                del buf[:fs + 2]
                # Decodificar (UTF-8 por defecto; puedes aplicar fallback si falla)
                try:
                    msg = payload.decode('utf-8')
                except UnicodeDecodeError:
                    msg = payload.decode('latin-1')
                yield msg
            except ValueError:
                # No hay FS aún
                break

class TcpSender:
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host; self.port = port; self.timeout = timeout

    async def send(self, hl7_text: str) -> None:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout=self.timeout)
        writer.write(hl7_text.encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()


class TcpServer:
    def __init__(self, host: str, port: int, on_message_async):
        self.host = host; self.port = port; self.on_message_async = on_message_async
        self._server = None

    async def _handle(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            async for hl7 in read_mllp_messages(reader):
                await self.on_message_async(hl7, peer)
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        async with self._server:
            await self._server.serve_forever()
