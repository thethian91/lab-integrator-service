from typing import Any, Dict

import yaml

from app.commons.hl7_normalizer import HL7Normalizer
from app.parsers.models import NormalizedResult


class HL7Engine:
    """Engine facade that loads config and exposes parse/map methods.
    Existing code calling HL7Engine(template_yaml) seguirá funcionando.
    """

    def __init__(self, config_path_or_obj: Any):
        # Soportar rutas o dict ya cargado
        if isinstance(config_path_or_obj, str):
            with open(config_path_or_obj, "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f)
        elif isinstance(config_path_or_obj, dict):
            self.cfg = config_path_or_obj
        else:
            self.cfg = {}

        parsers_cfg = self.cfg.get("parsers", {})
        autodetect = bool(parsers_cfg.get("autodetect", True))
        override = parsers_cfg.get("override", "")
        self.normalizer = HL7Normalizer(autodetect=autodetect, override=override)

    def normalize(self, hl7_text: str) -> NormalizedResult:
        return self.normalizer.normalize(hl7_text)

    def to_sofia_payload(self, norm: NormalizedResult) -> Dict:
        return self.normalizer.to_sofia_payload(norm)

    def parse_and_map(self, hl7_text: str) -> Dict:
        norm = self.normalize(hl7_text)
        return self.to_sofia_payload(norm)
