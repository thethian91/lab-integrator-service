from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class Patient(BaseModel):
    tipo_doc: str
    num_doc: str
    name: str
    last_name: str
    born_date: str
    gender: str


class OrderItem(BaseModel):
    order_id: str
    placer_id: Optional[str] = None
    codigo: str
    description: str
    date_orden: str
    date_test: str  # f echa muestra


class OrderPayload(BaseModel):
    paciente: Patient
    atencion: Dict[str, Any]
    meta: Dict[str, Any]
    ordenes: List[OrderItem]


class TransportCfg(BaseModel):
    type: Literal["file", "tcp"]
    file: Dict[str, Any] = {}
    tcp: Dict[str, Any] = {}


class Settings(BaseModel):
    app: Dict[str, Any]
    paths: Dict[str, str]
    transport: Dict[str, TransportCfg]
    engine: Dict[str, str]
    retry: Dict[str, Any]
