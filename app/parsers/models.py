# ===============================
# File: app/parsers/models.py
# ===============================
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Patient:
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    id: Optional[str] = None
    dob: Optional[str] = None  # YYYYMMDD


@dataclass
class Observation:
    code: str
    text: Optional[str]
    value: Optional[str]
    units: Optional[str]
    status: Optional[str] = None
    ref_range: Optional[str] = None
    measured_at: Optional[str] = None  # OBX-14 if present
    raw: Dict = None


@dataclass
class OrderInfo:
    placer_order: Optional[str] = None
    filler_order: Optional[str] = None
    sample_type: Optional[str] = None
    collection_dt: Optional[str] = None  # YYYYMMDDHHMMSS


@dataclass
class NormalizedResult:
    analyzer: str
    hl7_version: str
    patient: Patient
    order: OrderInfo
    observations: List[Observation]
    extras: Dict
