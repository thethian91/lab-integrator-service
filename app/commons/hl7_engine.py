"""
hl7_engine.py

HL7 Engine for parsing, transforming, and sending messages
between medical analyzers and the Sofia REST API.

Responsibilities:
- Load HL7 templates from YAML config.
- Parse and transform lab orders/results.
- Provide structured output for Sofia integration.

Author: Cristian Giraldo / VITRONIX
Created: 2025-08-18
"""

import datetime as dt
import re
from typing import Any, Dict, List, Optional, Union

import yaml

AT_PATTERN = re.compile(r"(?<!@)@([A-Z0-9_]+)")  # @PLACEHOLDER (evita @@)
ESCAPED_AT = re.compile(r"@@")


class HL7Engine:
    def __init__(self, config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.sep = {
            "field": self.cfg["hl7"]["field_sep"],
            "comp": self.cfg["hl7"]["comp_sep"],
            "rep": self.cfg["hl7"]["rep_sep"],
            "esc": self.cfg["hl7"]["esc"],
            "sub": self.cfg["hl7"]["subcomp_sep"],
        }
        self.options = self.cfg.get("options", {})
        self.defaults = self.cfg.get("defaults", {})
        self.mappings = self.cfg.get("mappings", {})

    def hl7_unescape(self, text: str) -> str:
        if text is None:
            return ""
        esc = self.sep["esc"]  # normalmente '\'
        return (
            text.replace(f"{esc}F{esc}", self.sep["field"])  # \F\ -> |
            .replace(f"{esc}S{esc}", self.sep["comp"])  # \S\ -> ^
            .replace(f"{esc}R{esc}", self.sep["rep"])  # \R\ -> ~
            .replace(f"{esc}E{esc}", self.sep["esc"])  # \E\ -> \
            .replace(f"{esc}T{esc}", self.sep["sub"])
        )  # \T\ -> &

    # --- NUEVO: detectar separadores desde MSH y normalizar saltos ---
    def _normalize_newlines(self, msg: str) -> str:
        # Acepta CRLF, LF o CR; estandariza a CR (\r) para todo el engine
        return re.sub(r"(?:\r\n|\n|\r)", "\r", msg.strip())

    def _detect_and_apply_separators(self, msg: str) -> None:
        r"""
        Lee el primer segmento MSH y ajusta self.sep a los declarados en el mensaje.
        HL7: MSH-1 = field separator (el char en posición 3 del segmento "MSHx")
            MSH-2 = encoding chars: comp^rep~esc\sub&
        """
        norm = self._normalize_newlines(msg)
        first = norm.split("\r", 1)[0]
        if not first.startswith("MSH"):
            return  # no MSH, deja como está
        field_sep = first[3]
        parts = first.split(field_sep)
        if len(parts) < 2:
            return
        enc = parts[1] or "^~\\&"
        comp = enc[0] if len(enc) > 0 else "^"
        rep = enc[1] if len(enc) > 1 else "~"
        esc = enc[2] if len(enc) > 2 else "\\"
        sub = enc[3] if len(enc) > 3 else "&"
        self.sep.update({"field": field_sep, "comp": comp, "rep": rep, "esc": esc, "sub": sub})

    # ------------- PARSEO BÁSICO HL7 -------------
    def split_segments(self, msg: str) -> List[str]:
        msg = self._normalize_newlines(msg)
        return [s for s in msg.split("\r") if s]

    def get_segment_fields(self, segment: str) -> List[str]:
        return segment.split(self.sep["field"])

    def get_field(
        self, field_val: str, comp_idx: Optional[int] = None, sub_idx: Optional[int] = None
    ) -> str:
        if comp_idx is None:
            return field_val
        comps = field_val.split(self.sep["comp"])
        if comp_idx - 1 >= len(comps):
            return ""
        comp_val = comps[comp_idx - 1]
        if sub_idx is None:
            return comp_val
        subs = comp_val.split(self.sep["sub"])
        return subs[sub_idx - 1] if sub_idx - 1 < len(subs) else ""

    def parse_path(self, path: str):
        # Ej: "OBX-5(2)-1" -> seg="OBX", field=5, rep=2, comp=1, sub=None
        m = re.fullmatch(r"([A-Z0-9]{3})-([0-9]+)(?:\((\d+)\))?(?:-([0-9]+))?(?:-([0-9]+))?", path)
        if not m:
            raise ValueError(f"Path HL7 inválido: {path}")
        seg, field, rep, comp, sub = m.groups()
        return (
            seg,
            int(field),
            int(rep) if rep else 1,
            int(comp) if comp else None,
            int(sub) if sub else None,
        )

    def get_value_from_hl7(self, hl7_msg: str, path: str) -> str:
        # Asegura separadores correctos por mensaje
        self._detect_and_apply_separators(hl7_msg)
        seg_name, field_idx, rep_idx, comp_idx, sub_idx = self.parse_path(path)
        segments = [
            s for s in self.split_segments(hl7_msg) if s.startswith(seg_name + self.sep["field"])
        ]
        if not segments:
            return ""
        seg = segments[0]
        fields = self.get_segment_fields(seg)
        if field_idx >= len(fields):
            return ""
        reps = fields[field_idx].split(self.sep["rep"])
        if rep_idx - 1 >= len(reps):
            return ""
        field_val = reps[rep_idx - 1]
        return self.get_field(field_val, comp_idx, sub_idx)

    # ------------- TRANSFORMACIONES -------------
    def apply_transforms(self, value: Any, transforms: List[str]) -> str:
        val = "" if value is None else str(value)
        for t in transforms:
            if t == "upper":
                val = val.upper()
            elif t == "lower":
                val = val.lower()
            elif t == "trim":
                val = val.strip()
            elif t.startswith("datefmt:"):
                fmt = t.split(":", 1)[1]
                dt_obj = self._parse_guess_datetime(val)
                val = dt_obj.strftime(fmt) if dt_obj else val
            elif t.startswith("padleft:"):
                width = int(t.split(":", 1)[1])
                val = val.rjust(width, "0")
            # Nota: datefmt_in/out se manejan aparte donde aplique
        return val

    def apply_date_in_out(self, value: str, t_in: str, t_out: str) -> str:
        try:
            dt_obj = dt.datetime.strptime(value, t_in)
            return dt_obj.strftime(t_out)
        except Exception:
            return value

    def _parse_guess_datetime(self, text: str) -> Optional[dt.datetime]:
        for fmt in (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y%m%d",
            "%Y%m%d%H%M%S",
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M:%S",
        ):
            try:
                return dt.datetime.strptime(text, fmt)
            except Exception:
                pass
        return None

    # ------------- SOURCES PARA RENDER -------------
    def get_source_value(self, spec: str, data: Dict[str, Any], hl7_in: Optional[str]) -> Any:
        if spec.startswith("DATA:"):
            path = spec[5:]
            return self._get_from_dict_path(data, path)
        elif spec.startswith("HL7:"):
            if not hl7_in:
                return ""
            path = spec[4:]
            return self.get_value_from_hl7(hl7_in, path)
        else:
            return spec  # literal

    def _get_from_dict_path(self, dct: Dict[str, Any], path: str) -> Any:
        cur: Any = dct
        for part in re.split(r"\.", path):
            m = re.fullmatch(r"([A-Za-z0-9_]+)(?:\[(\d+)\])?", part)
            if not m:
                return None
            key, idx = m.groups()
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
            if idx is not None:
                cur = cur[int(idx)]
        return cur

    # ------------- RENDER (con soporte for_each) -------------
    def render(self, template_name: str, data: Dict[str, Any], hl7_in: Optional[str] = None) -> str:
        tmpl = self.cfg["templates"][template_name]
        lines: List[str] = []
        for raw in tmpl:
            if isinstance(raw, str):
                line = self._render_line(raw, data, hl7_in)
                lines.append(line)
            elif isinstance(raw, dict) and "for_each" in raw and "lines" in raw:
                coll_path = raw["for_each"]  # p.ej. "ordenes"
                sub_lines: List[str] = raw["lines"]
                items = self._get_from_dict_path(data, coll_path) or []
                if not isinstance(items, list):
                    continue
                for item in items:
                    # @THIS.* dentro de sub_lines
                    for sub_raw in sub_lines:
                        line = self._render_line(sub_raw, data, hl7_in, this=item)
                        lines.append(line)
            else:
                # Ignorar definiciones no soportadas
                continue
        return "\r".join(str(x) for x in lines) + "\r"

    def _render_line(
        self,
        raw_line: str,
        data: Dict[str, Any],
        hl7_in: Optional[str],
        this: Optional[Dict[str, Any]] = None,
    ) -> str:
        line = raw_line

        # Soporte para @THIS.campo
        def replace_this(m):
            key = m.group(1)
            return str(self._get_from_dict_path(this or {}, key) or "")

        line = re.sub(r"@THIS\.([A-Za-z0-9_.\[\]]+)", replace_this, line)

        if self.options.get("escape_at", True):
            line = ESCAPED_AT.sub("__AT_LITERAL__", line)

        def repl(m):
            name = m.group(1)
            mapdef = self.mappings.get(name)
            if not mapdef:
                policy = self.options.get("missing_placeholder", "error")
                if policy == "keep":
                    return "@" + name
                elif policy == "empty":
                    return ""
                else:
                    raise KeyError(f"Placeholder @{name} no tiene mapping en config.")
            src = mapdef.get("source", "")
            val = self.get_source_value(src, data, hl7_in)
            if (val is None or val == "") and name.lower() in self.defaults:
                val = self.defaults[name.lower()]
            transforms = mapdef.get("transforms", [])
            val = self.apply_transforms(val, transforms)
            return val

        line = AT_PATTERN.sub(repl, line)
        if self.options.get("escape_at", True):
            line = line.replace("__AT_LITERAL__", "@")
        return line

    # ------------- EXTRACT SIMPLE (no agrupado) -------------
    def extract(self, profile: str, hl7_msg: str) -> Dict[str, Any]:
        self._detect_and_apply_separators(hl7_msg)
        return self._extract_impl(profile, hl7_msg)

    def _extract_impl(self, profile: str, hl7_msg: str) -> Dict[str, Any]:
        """Implementación base de extractores declarativos (sección YAML: extractors)."""
        rules = self.cfg["extractors"][profile]
        out: Dict[str, Any] = {}
        for r in rules:
            name = r["name"]
            path = r["path"]
            transforms = r.get("transforms", [])

            # 1) obtener valor crudo por path
            val = self.get_value_from_hl7(hl7_msg, path)

            # 2) aplicar datefmt_in/out si vienen en pareja
            t_in = next(
                (t.split(":", 1)[1] for t in transforms if t.startswith("datefmt_in:")), None
            )
            t_out = next(
                (t.split(":", 1)[1] for t in transforms if t.startswith("datefmt_out:")), None
            )
            if t_in and t_out:
                val = self.apply_date_in_out(val, t_in, t_out)

            # 3) aplicar las demás transformaciones
            std = [t for t in transforms if not t.startswith("datefmt_")]
            val = self.apply_transforms(val, std)

            # 4) asignar al dict de salida siguiendo la ruta 'name'
            self._assign_to_dict_path(out, name, val)
        return out

    def _assign_to_dict_path(self, dct: Dict[str, Any], path: str, value: Any):
        parts = re.split(r"\.", path)
        cur = dct
        for i, part in enumerate(parts):
            m = re.fullmatch(r"([A-Za-z0-9_]+)(?:\[(\d+)\])?", part)
            if not m:
                raise ValueError(f"Ruta de salida inválida: {path}")
            key, idx = m.groups()
            if i == len(parts) - 1:
                if idx is None:
                    cur[key] = value
                else:
                    cur.setdefault(key, [])
                    lst = cur[key]
                    idx_int = int(idx)
                    while len(lst) <= idx_int:
                        lst.append({})
                    lst[idx_int] = value
            else:
                if idx is None:
                    cur = cur.setdefault(key, {})
                else:
                    cur.setdefault(key, [])
                    lst = cur[key]
                    idx_int = int(idx)
                    while len(lst) <= idx_int:
                        lst.append({})
                    cur = lst[idx_int]

    # ------------- ITERACIÓN ORDENADA DE SEGMENTOS -------------
    def iter_segments(self, hl7_msg: str):
        for line in self.split_segments(hl7_msg):
            parts = self.get_segment_fields(line)
            if not parts:
                continue
            seg = parts[0]
            yield seg, parts

    def _get_field_from_parts(
        self, parts: List[str], field_idx: int, comp_idx: Optional[int], sub_idx: Optional[int]
    ) -> str:
        if field_idx >= len(parts):
            return ""
        reps = parts[field_idx].split(self.sep["rep"])
        field_val = reps[0] if reps else ""
        return self.get_field(field_val, comp_idx, sub_idx)

    def _value_by_path_from_parts(self, parts: List[str], path: str) -> str:
        _, field, _rep, comp, sub = self.parse_path(path)
        val = self._get_field_from_parts(parts, field, comp, sub)
        return self.hl7_unescape(val)

    # ------------- EXTRACT AGRUPADO OBR -> OBX -------------
    def extract_grouped(
        self, profile: str, hl7_msg: str, base_out: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        self._detect_and_apply_separators(hl7_msg)
        cfg = self.cfg["group_extractors"][profile]

        if "group_extractors" not in self.cfg or profile not in self.cfg["group_extractors"]:
            raise KeyError(f"Perfil '{profile}' no encontrado en group_extractors del YAML.")

        cfg = self.cfg["group_extractors"][profile]
        base_seg = cfg["base"]  # "OBR"
        assign_root = cfg["assign"]  # "ordenes[*]"
        obr_fields = cfg.get(
            "fields", {}
        )  # dict con "obr.xxx": "OBR-4-1" o {"path": "...", "transforms":[...]}
        child = cfg["children"]
        child_seg = child["base"]  # "OBX"
        child_assign = child["assign"]  # "examenes[*]"
        child_fields = child.get("fields", {})

        out = base_out if base_out is not None else {}

        current_group_index = -1
        current_child_index_for_group: Dict[int, int] = {}

        for seg_name, parts in self.iter_segments(hl7_msg):
            if seg_name == base_seg:
                current_group_index += 1
                current_child_index_for_group[current_group_index] = 0
                # Campos del OBR actual
                for name, spec in obr_fields.items():
                    path, transforms = self._normalize_field_spec(spec)
                    val = self._value_by_path_from_parts(parts, path)
                    val = self._apply_possible_date_transforms(val, transforms)
                    val = self.apply_transforms(
                        val, [t for t in transforms if not t.startswith("datefmt_")]
                    )
                    self._assign_to_dict_path(
                        out,
                        assign_root.replace("[*]", f"[{current_group_index}]") + "." + name,
                        val,
                    )

            elif seg_name == child_seg and current_group_index >= 0:
                # Campos del OBX perteneciente al OBR vigente
                child_index = current_child_index_for_group[current_group_index]
                base_path = (
                    assign_root.replace("[*]", f"[{current_group_index}]")
                    + "."
                    + child_assign.replace("[*]", f"[{child_index}]")
                )
                for name, spec in child_fields.items():
                    path, transforms = self._normalize_field_spec(spec)
                    val = self._value_by_path_from_parts(parts, path)
                    val = self._apply_possible_date_transforms(val, transforms)
                    val = self.apply_transforms(
                        val, [t for t in transforms if not t.startswith("datefmt_")]
                    )
                    self._assign_to_dict_path(out, base_path + f".{name}", val)
                current_child_index_for_group[current_group_index] += 1

        return out

    def _normalize_field_spec(self, spec: Union[str, Dict[str, Any]]) -> (str, List[str]):
        if isinstance(spec, str):
            return spec, []
        return spec.get("path", ""), spec.get("transforms", [])

    def _apply_possible_date_transforms(self, value: str, transforms: List[str]) -> str:
        t_in = next((t.split(":", 1)[1] for t in transforms if t.startswith("datefmt_in:")), None)
        t_out = next((t.split(":", 1)[1] for t in transforms if t.startswith("datefmt_out:")), None)
        if t_in and t_out:
            return self.apply_date_in_out(value, t_in, t_out)
        return value
