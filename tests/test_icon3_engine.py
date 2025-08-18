"""
test_icon3_engine.py

Unit tests for the ICON3 analyzer integration module.

Covers:
- Order generation and HL7 encoding.
- Parsing of analyzer results.
- Validation of message transformation.

Author: Cristian Giraldo / VITRONIX
"""

# import asyncio # noqa: E501
import pytest

from app.commons.hl7_engine import HL7Engine
from app.helpers.router import FlowRouter
from app.helpers.tcp_transport import CR, FS, VT, read_mllp_messages
from app.validation.validators import validate_hl7_message_or_raise

TEMPLATE_PATH = "./app/configs/template_reader_orm_hl7.yaml"  # ajusta ruta si es distinta


def make_engine():
    return HL7Engine(TEMPLATE_PATH)


def make_router(cfg: dict):
    eng = make_engine()
    return FlowRouter(eng, cfg)


def cfg_min():
    # Config mínima para extractores
    return {
        "paths": {
            "logs_root": "logs",
            "inbox": ".",
            "outbox": ".",
            "archive": "./archive",
            "error": "./error",
        },
        "engine": {
            "template": "ORM_O01_ORC_EACH",
            "extractor_profile": "OBR_OBX_GROUPED",
            "header_profile": "HEADER_PATIENT",
        },
    }


# ----------------- Muestras HL7 embebidas -----------------
CRONLY = "MSH|^~\\&|Icon|NI1|LIS|LIS|20250817141000||ORU^R01|X|P|2.5\rOBR|1|NEG003|||||20250817140900|\rOBX|1|NM|HGB^HEMOGLOBIN||145|^g/L|120-172|||N|F\r"

ALT_SEP = "MSH~*^!&~Icon~NI1~LIS~LIS~20250817141500~~ORU^R01~ALT~P~2.5\rOBR~1~ALT||||~20250817141400~\rOBX~1~NM~PLT*PLATELETS~~210~^10³/μL~172-440~~~H~F\r"

# Valor con * y < (normalización)
ASTER_LT = """MSH|^~\\&|Icon|ND30|LIS|LIS|20250817140000||ORU^R01|NEG-0001|P|2.5
OBR|1|NEG001|||||20250817135900|
OBX|1|NM|WBC^WBC||*7.7|^10³/μL|3.7-11.7||||F
OBX|2|NM|MCV^MCV||<30|^fL|78-96||||F
"""

# MLLP con dos mensajes
MLLP_TWO = (
    VT
    + b"MSH|^~\\&|Icon|ND|LIS|LIS|20250817142000||ORU^R01|A|P|2.5\rOBR|1|A|||||20250817141900|\rOBX|1|NM|HCT^HCT||39.5|^%|35-51|||N|F\r"
    + FS
    + CR
    + VT
    + b"MSH|^~\\&|Icon|ND|LIS|LIS|20250817142005||ORU^R01|B|P|2.5\rOBR|1|B|||||20250817141905|\rOBX|1|NM|RBC^RBC||4.58|^10^12/L|4.1-5.7|||N|F\r"
    + FS
    + CR
)

# Histograma mal (base64 corto)
HISTO_BAD = """MSH|^~\\&|Icon|NI1|LIS|LIS|20250817140500||ORU^R01|H|P|2.5
OBR|1|NEG|||||20250817140400|
OBX|1|ST|RBCHistogram||QUJDREVGRw==||||||F
"""

# Falta MSH-9
MISSING_MSH9 = """MSH|^~\\&|Icon|NI1|LIS|LIS|20250817140500||||H|P|2.5
OBR|1|X|||||20250817140400|
"""


# ----------------- Tests -----------------
def test_separators_cr_only():
    eng = make_engine()
    # No debe explotar; split debe encontrar 3 segmentos
    segs = eng.split_segments(CRONLY)
    assert len(segs) == 3
    # Y debe poder leer OBX-5
    val = eng.get_value_from_hl7(CRONLY, "OBX-5")
    assert val == "145"


def test_separators_alternate():
    eng = make_engine()
    # Debe detectar ~ como field, * como comp
    val_code = eng.get_value_from_hl7(ALT_SEP, "OBX-3-1")
    val_value = eng.get_value_from_hl7(ALT_SEP, "OBX-5")
    assert val_code == "PLT"
    assert val_value == "210"


def test_normalize_values_on_router():
    router = make_router(cfg_min())
    data = router.extract_results(ASTER_LT)
    ex1 = data["ordenes"][0]["examenes"][0]["valor_norm"]  # *7.7
    ex2 = data["ordenes"][0]["examenes"][1]["valor_norm"]  # <30
    assert ex1["flagged"] is True and ex1["numeric"] == 7.7
    assert ex2["qualifier"] == "<" and ex2["numeric"] == 30.0


@pytest.mark.asyncio
async def test_mllp_two_messages_reader():
    async def run():
        msgs = []

        async def fake_reader():
            # Emula StreamReader.read con iteración única
            yield MLLP_TWO

        # Reemplazo simple del reader.read
        class DummyReader:
            def __init__(self, data):
                self._data = data
                self._done = False

            async def read(self, n):
                if self._done:
                    return b""
                self._done = True
                return self._data

        reader = DummyReader(MLLP_TWO)
        async for m in read_mllp_messages(reader):
            msgs.append(m)
        return msgs

    msgs = await run()
    assert len(msgs) == 2
    assert "MSG" not in msgs[0] or msgs[0].startswith("MSH|")
    assert msgs[1].startswith("MSH|")


def test_histogram_bad_raises_validationerror():
    with pytest.raises(Exception):
        validate_hl7_message_or_raise(HISTO_BAD)


def test_missing_msh9_raises_validationerror():
    with pytest.raises(Exception):
        validate_hl7_message_or_raise(MISSING_MSH9)
