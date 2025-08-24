import re
from typing import Dict

from app.parsers.base import detect_profile
from app.parsers.finecare import parse_finecare
from app.parsers.icon3 import parse_icon3
from app.parsers.models import NormalizedResult


class HL7Normalizer:
    def __init__(self, autodetect: bool = True, override: str = ""):
        self.autodetect = autodetect
        self.override = (override or "").upper()

    def normalize(self, hl7_text: str) -> NormalizedResult:
        profile = self.override or (detect_profile(hl7_text) if self.autodetect else "FINECARE")
        if profile == "ICON3":
            return parse_icon3(hl7_text)
        return parse_finecare(hl7_text)

    def to_sofia_payload(self, norm: NormalizedResult) -> Dict:
        """Map normalized result into a generic payload expected by SOFIA API.
        Adjust keys if your API contract differs.
        """
        return {
            "analyzer": norm.analyzer,
            "hl7_version": norm.hl7_version,
            "patient": {
                "external_id": norm.patient.id,
                "name": norm.patient.name,
                "dob": norm.patient.dob,
                "age": norm.patient.age,
                "sex": norm.patient.sex,
            },
            "order": {
                "placer_order": norm.order.placer_order,
                "filler_order": norm.order.filler_order,
                "sample_type": norm.order.sample_type,
                "collection_dt": norm.order.collection_dt,
            },
            "results": [
                {
                    "test_code": o.code,
                    "test_name": o.text,
                    "value": o.value,
                    "units": o.units,
                    "ref_range": o.ref_range,
                    "status": o.status,
                    "measured_at": o.measured_at,
                }
                for o in norm.observations
            ],
            "extras": norm.extras,
        }

        # -------- Compat helpers usados por tests --------

    def split_segments(self, hl7_text: str):
        """Divide en segmentos HL7 (CR/LF), omite vacíos."""
        return [s for s in re.split(r"\r\n|\n|\r", hl7_text) if s]

    def _seps(self, hl7_text: str):
        """
        Detecta separadores desde MSH:
        - field sep = MSH[3]
        - encoding chars (MSH-2): comp, rept, esc, subcomp
        """
        first_msh = next((s for s in self.split_segments(hl7_text) if s.startswith("MSH")), "")
        # Defaults HL7
        seps = {"f": "|", "c": "^", "r": "~", "e": "\\", "s": "&"}
        if not first_msh or len(first_msh) < 4:
            return seps
        field_sep = first_msh[3]
        fields = first_msh.split(field_sep)
        enc = fields[1] if len(fields) > 1 else "^~\\&"
        comp = enc[0] if len(enc) > 0 else "^"
        rept = enc[1] if len(enc) > 1 else "~"
        esc = enc[2] if len(enc) > 2 else "\\"
        sub = enc[3] if len(enc) > 3 else "&"
        return {"f": field_sep, "c": comp, "r": rept, "e": esc, "s": sub}

    def get_value_from_hl7(self, hl7_text: str, path: str):
        """
        Extrae un valor por ruta tipo 'SEG-<field>[-<component>]',
        e.g. 'OBX-3-1'. Respeta separadores detectados.
        """
        seps = self._seps(hl7_text)
        f, c = seps["f"], seps["c"]
        parts = path.split("-")
        seg = parts[0].strip().upper()
        if len(parts) < 2:
            return None
        field_idx = int(parts[1])
        comp_idx = int(parts[2]) - 1 if len(parts) > 2 else None

        seg_line = next(
            (line for line in self.split_segments(hl7_text) if line.startswith(seg + f)), None
        )
        if not seg_line:
            return None

        fields = seg_line.split(f)
        # Nota: Para MSH la numeración HL7 está desplazada (MSH-2 => fields[1])
        idx = field_idx - 1 if seg == "MSH" else field_idx
        if idx < 0 or idx >= len(fields):
            return None
        val = fields[idx]
        if comp_idx is not None:
            comps = val.split(c) if val is not None else []
            return comps[comp_idx] if 0 <= comp_idx < len(comps) else None
        return val

    def extract(self, profile, hl7_text: str):
        """
        Soporte simple: si 'profile' es { key: 'SEG-x-y' | [paths] } devuelve dict con valores.
        (Back-compat para tests/routers que llamen engine.extract)
        """
        out = {}
        if isinstance(profile, dict):
            for k, p in profile.items():
                if isinstance(p, str):
                    out[k] = self.get_value_from_hl7(hl7_text, p)
                elif isinstance(p, (list, tuple)):
                    out[k] = [self.get_value_from_hl7(hl7_text, q) for q in p]
        return out
