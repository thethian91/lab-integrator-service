from typing import List

from .base import _split_comp, _split_fields
from .models import NormalizedResult, Observation, OrderInfo, Patient


def parse_finecare(hl7: str) -> NormalizedResult:
    # Normaliza líneas y descarta vacías
    lines = [line for line in hl7.splitlines() if line.strip()]

    # Segmentos principales
    msh = next((line for line in lines if line.startswith("MSH")), "")
    pid = next((line for line in lines if line.startswith("PID")), "")
    obr = next((line for line in lines if line.startswith("OBR")), "")

    # MSH
    f = _split_fields(msh)
    version = f[11] if len(f) > 11 else "2.4"

    # PID
    p = _split_fields(pid) if pid else []
    name = None
    if len(p) > 5 and p[5]:
        comp = _split_comp(p[5])  # last^first normalmente
        # apellido^nombre → "nombre apellido"; si no hay ^, usa tal cual
        name = (comp[1] + " " + comp[0]).strip() if len(comp) > 1 else p[5]

    patient = Patient(
        name=name or None,
        dob=(p[7] if len(p) > 7 else None),
        sex=(p[8] if len(p) > 8 else None),
        id=(p[3] if len(p) > 3 else None),
    )

    # OBR
    o = _split_fields(obr) if obr else []
    order = OrderInfo(
        placer_order=o[1] if len(o) > 1 else None,
        filler_order=o[2] if len(o) > 2 else None,
        collection_dt=o[7] if len(o) > 7 else None,
        sample_type=o[18] if len(o) > 18 else None,
    )

    # OBX (observaciones)
    observations: List[Observation] = []
    for line in lines:
        if not line.startswith("OBX|"):
            continue

        o = _split_fields(line)

        # Inicializa campos
        code = ""
        text = None
        value = None
        units = None
        ref_range = None
        status = None
        measured_at = None

        # OBX-3: CE -> "code^text" o solo "code"
        raw_obx3 = o[3] if len(o) > 3 else ""
        comp = _split_comp(raw_obx3) if raw_obx3 else []
        if comp:
            code = comp[0] if len(comp) > 0 else (raw_obx3 or "")
            text = comp[1] if len(comp) > 1 else None
        else:
            code = raw_obx3 or ""

        # Fallback 1: algunos Finecare ponen el nombre del analito en OBX-4 (texto plano)
        if (not text) and len(o) > 4 and o[4] and "^" not in o[4]:
            text = o[4]

        # Valores comunes
        value = o[5] if len(o) > 5 and o[5] != "" else None
        units = o[6] if len(o) > 6 and o[6] != "" else None
        ref_range = o[7] if len(o) > 7 and o[7] != "" else None

        # Fallback 2: a veces meten "Testosterone^16" en OBX-9 (!)
        if (not text or not code) and len(o) > 9 and o[9] and "^" in o[9]:
            tcomp = _split_comp(o[9])
            if len(tcomp) >= 2:
                a, b = tcomp[0], tcomp[1]
                a_is_num, b_is_num = a.isdigit(), b.isdigit()
                if not a_is_num and b_is_num:
                    text = text or a
                    code = code or b
                elif a_is_num and not b_is_num:
                    code = code or a
                    text = text or b
                else:
                    text = text or a

        status = o[11] if len(o) > 11 and o[11] != "" else None
        measured_at = o[14] if len(o) > 14 and o[14] != "" else None

        observations.append(
            Observation(
                code=code,
                text=text,
                value=value,
                units=units,
                status=status,
                ref_range=ref_range,
                measured_at=measured_at,
                raw={"segment": line},
            )
        )

    analyzer = _split_fields(msh)[2] if msh else "QIAnalyzer"
    return NormalizedResult(
        analyzer=analyzer or "QIAnalyzer",
        hl7_version=version,
        patient=patient,
        order=order,
        observations=observations,
        extras={},
    )
