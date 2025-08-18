# app/validation/validators.py
import base64
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator


class HistogramPayload(BaseModel):
    name: Literal["RBCHistogram", "PLTHistogram", "WBCHistogram"]
    data_b64: str

    @field_validator("data_b64")
    @classmethod
    def _validate_len(cls, v: str):
        # Decodifica y exige 256 bytes exactos
        try:
            raw = base64.b64decode(v, validate=True)
        except Exception as ex:
            raise ValueError(f"Histogram base64 inválido: {ex}")
        if len(raw) != 256:
            raise ValueError(f"Histogram inválido: longitud {len(raw)} != 256")
        return v


class HL7MessageMeta(BaseModel):
    msh_9: str  # Debe existir (ej: "ORU^R01")

    @field_validator("msh_9")
    @classmethod
    def _not_empty(cls, v: str):
        if not v or not v.strip():
            raise ValueError("MSH-9 es obligatorio")
        return v


class ResultValidation(BaseModel):
    header: HL7MessageMeta
    histograms: List[HistogramPayload] = []


# --------- Utilidades para construir el modelo desde el HL7 ----------
def parse_msh9_from_text(hl7_text: str) -> Optional[str]:
    # Toma separador de campo real desde MSH (posición 3)
    text = re.sub(r"(?:\r\n|\n|\r)", "\r", hl7_text.strip())
    first = text.split("\r", 1)[0]
    if not first.startswith("MSH"):
        return None
    field_sep = first[3]
    parts = first.split(field_sep)
    # MSH-9 suele ser "ORU^R01"
    return parts[8] if len(parts) > 8 else None


def collect_histograms_from_text(hl7_text: str) -> List[HistogramPayload]:
    text = re.sub(r"(?:\r\n|\n|\r)", "\r", hl7_text.strip())
    first = text.split("\r", 1)[0]
    field_sep = first[3] if len(first) > 3 else "|"
    enc = first.split(field_sep)[1] if field_sep in first else "^~\\&"
    comp = enc[0] if len(enc) > 0 else "^"

    out = []
    for seg in filter(None, text.split("\r")):
        if not seg.startswith("OBX" + field_sep):
            continue
        fields = seg.split(field_sep)
        # OBX-3 (identifier) y OBX-5 (valor)
        ident = fields[3] if len(fields) > 3 else ""
        value = fields[5] if len(fields) > 5 else ""
        code = ident.split(comp)[0] if ident else ""
        if code in ("RBCHistogram", "PLTHistogram", "WBCHistogram"):
            out.append(HistogramPayload(name=code, data_b64=value))
    return out


def validate_hl7_message_or_raise(hl7_text: str):
    """Construye el modelo y levanta ValidationError si algo falta/está mal."""
    msh9 = parse_msh9_from_text(hl7_text) or ""
    histos = collect_histograms_from_text(hl7_text)
    # Esto lanzará si MSH-9 falta o histogramas no son de 256 bytes
    ResultValidation(header=HL7MessageMeta(msh_9=msh9), histograms=histos)
