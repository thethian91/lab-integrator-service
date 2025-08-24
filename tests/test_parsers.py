# flake8: noqa

from app.commons.hl7_normalizer import HL7Normalizer

ICON3 = """MSH|^~\&|Icon-3|NI30H24105 |LIS Application|LIS|20250811095739||ORU^R01|638905030599480000|P|2.5||||||UNICODE UTF-8
SFT|N|1.3.2596.0|Icon-3|1.3.2596.0|Product Version: 0.9 Software complete version: 1.3.2596.0(FE - 00 - 45)|20240124034738
OBR||||^^^570^1145654765||||20250811095735|25||||3 Part Differential Hematology
NTE|Comment1||juancho correlon|1^Name
NTE|Comment2||55|2^Age
OBX|||0^RBC||4.03|^10⁶/μL|3.85-5.78||||F
"""

FINECARE = """MSH|^~\&|QIAnalyzer|荧光定量分析仪^FS1142411205376^FS-114||^^|20250822223809||ORU^R01^ORU_R01|688|P|2.4||||0|CHN|Unicode||||
PID|689||^1130609729^||JORGE Rojas||19690822|M||||||||||||||||||||||||||||
OBR|FS1142411205376_14_20250821052417|F2481660E|14||||20250821052417||||||||Suero / plasma|||||||||||||||||||||||||||||||
OBX|FS1142411205376_14_20250821052417_0|NM|16|Testosterone|7.55|ng/mL|Masculino: 20-49 Años: 1.91-8.41;Masculino: ≥50 Años: 1.61-8.01;Mujer: 20-49 Años: ≤0.80;Mujer: ≥50 Años: ≤0.71|Testosterone^16|||F||7.55132|20250821052417||||||
"""


def test_icon3_name_and_age():
    n = HL7Normalizer(autodetect=True)
    res = n.normalize(ICON3)
    assert res.patient.name == "juancho correlon"
    assert res.patient.age == 55
    assert any(o.code == "0" and o.text == "RBC" for o in res.observations)


def test_finecare_pid_parsing():
    n = HL7Normalizer(autodetect=True)
    res = n.normalize(FINECARE)
    assert res.patient.name.startswith("JORGE")
    assert res.patient.sex == "M"
    assert res.patient.dob == "19690822"
    assert any(o.code == "16" and o.text == "Testosterone" for o in res.observations)


def test_sofia_payload_shape():
    n = HL7Normalizer(autodetect=True)
    payload = n.to_sofia_payload(n.normalize(FINECARE))
    assert "patient" in payload and "results" in payload
    assert isinstance(payload["results"], list)
