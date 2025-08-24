from typing import List


def _split_fields(seg: str) -> List[str]:
    return seg.split("|")


def _split_comp(val: str) -> List[str]:
    return val.split("^") if val else []


def detect_profile(hl7: str) -> str:
    """Return 'ICON3' or 'FINECARE'."""
    lines = [line for line in hl7.splitlines() if line.strip()]
    msh = next((line for line in lines if line.startswith("MSH")), "")
    sft = next((line for line in lines if line.startswith("SFT")), "")
    f = _split_fields(msh)
    sending_app = f[2] if len(f) > 2 else ""
    version = f[11] if len(f) > 11 else ""

    if "Icon-3" in sending_app or "Icon-3" in sft:
        return "ICON3"
    if "QIAnalyzer" in sending_app:
        return "FINECARE"
    if "UNICODE UTF-8" in msh and version.startswith("2.5"):
        return "ICON3"
    return "FINECARE"
