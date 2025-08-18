import re
from app.commons.hl7_engine import HL7Engine
from app.commons.logger import logger
from pathlib import Path
from datetime import datetime

def _replace_none(obj):
    if isinstance(obj, dict):
        return {k: _replace_none(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_none(x) for x in obj]
    elif obj is None:
        return ""
    return obj

class FlowRouter:
    def __init__(self, engine: HL7Engine, cfg):
        self.engine = engine
        self.cfg = cfg
        self.paths = cfg["paths"]

    def _parse_icon3_nte(self, hl7_text: str) -> dict:
        """
        Extrae:
          - profile: NTE|Profile||Human
          - RD: NTE|RD||36|RE^RBC Discriminator (fL)
          - WDn: NTE|WD0||32|RE^WBC Discriminator #0 (fL)
          - flags: NTE|<RBC/WBC/PLT> flags||a3  o  NTE|Comment6||X4N6|6^WBC flags
        """
        self.engine._detect_and_apply_separators(hl7_text)
        segs = self.engine.split_segments(hl7_text)
        s = self.engine.sep  # separadores actuales

        out = {"icon3": {"profile": None, "discriminators": {"RD": None, "WD": {}}, "flags": {}}}

        for seg in segs:
            if not seg.startswith("NTE" + s["field"]):
                continue
            fields = seg.split(s["field"])
            # Campos: NTE|x|source|comment|...
            f1 = fields[1] if len(fields) > 1 else ""
            f2 = fields[2] if len(fields) > 2 else ""
            f3 = fields[3] if len(fields) > 3 else ""
            f4 = fields[4] if len(fields) > 4 else ""
            f5 = fields[5] if len(fields) > 5 else ""

            tag = (f1 or "").lower()

            # Profile
            if tag == "profile":
                out["icon3"]["profile"] = f2 or f3 or f4 or f5
                continue

            # RD (RBC discriminator)
            if tag == "rd":
                val = f3 or f4
                name = f5.split(s["comp"], 1)[-1] if f5 else ""
                out["icon3"]["discriminators"]["RD"] = {"value": val, "name": name}
                continue

            # WDn (WBC discriminators #0..n)
            mwd = re.fullmatch(r'(wd)(\d+)', tag)
            if mwd:
                idx = int(mwd.group(2))
                val = f3 or f4
                name = f5.split(s["comp"], 1)[-1] if f5 else ""
                out["icon3"]["discriminators"]["WD"][idx] = {"value": val, "name": name}
                continue

            # Flags (dos estilos):
            # 1) "NTE|WBC flags||A3"
            # 2) "NTE|Comment6||X4N6|6^WBC flags"
            if "flags" in (f2 or "").lower():
                sys = (f2 or "").split()[0].upper()  # WBC/RBC/PLT
                code = f3 or f4 or f5
                out["icon3"]["flags"].setdefault(sys, []).append({"code": code})
                continue
            if "flags" in (f5 or "").lower():
                # severidad en f5 (p.ej. 6^WBC flags)
                sev = re.match(r'(\d+)', f5 or "")
                sys = "UNKNOWN"
                if "WBC" in (f5 or "").upper(): sys = "WBC"
                if "RBC" in (f5 or "").upper(): sys = "RBC"
                if "PLT" in (f5 or "").upper(): sys = "PLT"
                out["icon3"]["flags"].setdefault(sys, []).append({"code": f3 or f4, "severity": int(sev.group(1)) if sev else None})
                continue

        return out
    
    # --- NUEVO: normalizar OBX-5 (*, <, >, '-') ---
    def _normalize_obx_value(self, raw: str) -> dict:
        raw = (raw or "").strip()
        if raw == "":
            return {"raw": "", "flagged": False, "dashed": False, "qualifier": None, "numeric": None}
        if raw == "-":
            return {"raw": "-", "flagged": False, "dashed": True, "qualifier": None, "numeric": None}
        flagged = raw.startswith("*")
        val = raw[1:] if flagged else raw
        qualifier = None
        if val.startswith(("<", ">")):
            qualifier, val = val[0], val[1:]
        # intenta número
        try:
            num = float(val)
        except ValueError:
            num = None
        return {"raw": raw, "flagged": flagged, "dashed": False, "qualifier": qualifier, "numeric": num}
    
    def _postprocess_icon3(self, data: dict) -> dict:
        """ Añade normalización de OBX-5 y anota NTE ICON3. """
        # Normaliza exámenes
        for ord in data.get("ordenes", []):
            for ex in ord.get("examenes", []):
                ex["valor_norm"] = self._normalize_obx_value(ex.get("valor", ""))
        # Añade anotaciones NTE
        return data

    def archive_raw(self, direction: str, hl7_text: str, tag: str):
        base = Path(self.paths["logs_root"]) / "raw" / direction
        base.mkdir(parents=True, exist_ok=True)
        name = f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_{tag}.hl7'
        (base / name).write_text(hl7_text, encoding="utf-8")

    # Renderizar orden -> texto HL7
    def render_order(self, payload_dict: dict) -> str:
        return self.engine.render(self.cfg["engine"]["template"], payload_dict, hl7_in=None)

    # Extraer resultados -> dict
    def extract_results(self, hl7_text: str) -> dict:
        header_profile = self.cfg["engine"].get("header_profile")
        grouped_profile = self.cfg["engine"]["extractor_profile"]

        base = {}
        if header_profile:
            base = self.engine.extract(header_profile, hl7_text)

        data = self.engine.extract_grouped(grouped_profile, hl7_text, base_out=base)

        # Mezcla anotaciones NTE de ICON3
        annotations = self._parse_icon3_nte(hl7_text)
        data.update(annotations)

        return self._postprocess_icon3(_replace_none( data ))
        '''
        header_profile = self.cfg["engine"].get("header_profile")
        grouped_profile = self.cfg["engine"]["extractor_profile"]

        base = {}
        if header_profile:
            base = self.engine.extract(header_profile, hl7_text)

        # Agrega OBR/OBX sobre el diccionario base (ya con paciente/meta)
        return self.engine.extract_grouped(grouped_profile, hl7_text, base_out=base)
        '''
