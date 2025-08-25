from typing import Dict, List

from .base import _split_comp, _split_fields
from .models import NormalizedResult, Observation, OrderInfo, Patient


def parse_icon3(hl7: str) -> NormalizedResult:
    lines = [line for line in hl7.splitlines() if line.strip()]
    msh = next((line for line in lines if line.startswith("MSH")), "")
    f = _split_fields(msh)
    version = f[11] if len(f) > 11 else "2.5"

    patient = Patient()
    order = OrderInfo()
    observations: List[Observation] = []
    extras: Dict = {"raw_nte": [], "raw_histograms": {}}

    # NTE blocks: value en NTE-3; etiqueta en NTE-4 (p.ej. '1^Name', '2^Age')
    for line in lines:
        if line.startswith("NTE|"):
            n = _split_fields(line)
            label_comp = _split_comp(n[4] if len(n) > 4 else "")
            label = label_comp[1].lower() if len(label_comp) > 1 else ""
            value = n[3].strip() if len(n) > 3 else ""
            if label == "name" and value:
                patient.name = value
            elif label == "age" and value:
                try:
                    patient.age = int(value.split()[0])
                except Exception:
                    pass
            extras["raw_nte"].append(line)

    # OBR (algunos campos pueden venir vacíos)
    for line in lines:
        if line.startswith("OBR|"):
            fields = _split_fields(line)
            order.placer_order = fields[1] if len(fields) > 1 else None
            order.filler_order = fields[2] if len(fields) > 2 else None
            order.collection_dt = fields[7] if len(fields) > 7 else None
            order.sample_type = fields[18] if len(fields) > 18 else None
            break

    # OBX results
    for line in lines:
        try:
            if line.startswith("OBX|"):
                fields = _split_fields(line)

                code = ""
                text = None
                value = None
                units = None
                ref_range = None
                status = None

                # OBX-3: id^text (puede venir vacío)
                comp = _split_comp(fields[3] if len(fields) > 3 and fields[3] else "")
                if comp:
                    code = comp[0] if len(comp) > 0 else ""
                    text = comp[1] if len(comp) > 1 else None

                # OBX-5/6/7/11 con índices seguros
                value = fields[5] if len(fields) > 5 and fields[5] != "" else None
                units = fields[6] if len(fields) > 6 and fields[6] != "" else None
                ref_range = fields[7] if len(fields) > 7 and fields[7] != "" else None
                status = fields[11] if len(fields) > 11 and fields[11] != "" else None

                # Histogramas (RBC/PLT/WBC): base64 en OBX-5
                if (text or "").lower().endswith("histogram"):
                    extras["raw_histograms"][text] = value

                observations.append(
                    Observation(
                        code=code,
                        text=text,
                        value=value,
                        units=units,
                        status=status,
                        ref_range=ref_range,
                        raw={"segment": line},
                    )
                )
        except Exception as e:
            extras.setdefault("obx_errors", []).append({"segment": line, "error": str(e)})
            continue

    analyzer = _split_fields(msh)[2] if msh else "Icon-3"
    return NormalizedResult(
        analyzer=analyzer or "Icon-3",
        hl7_version=version,
        patient=patient,
        order=order,
        observations=observations,
        extras=extras,
    )
