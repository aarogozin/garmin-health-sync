from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ReportMetric:
    value: float | None
    minimum: float | None = None
    maximum: float | None = None
    standard: float | None = None

    @property
    def evaluation(self) -> str:
        if self.value is None or self.minimum is None or self.maximum is None:
            return "Not available"
        if self.value < self.minimum:
            return "Low"
        if self.value > self.maximum:
            return "High"
        return "Standard"


@dataclass(frozen=True, slots=True)
class SegmentMetric:
    mass: float | None
    percentage: float | None
    standard: float | None

    @property
    def evaluation(self) -> str:
        if self.mass is None or self.standard is None:
            return "Not available"
        tolerance = self.standard * 0.1
        if self.mass < self.standard - tolerance:
            return "Low"
        if self.mass > self.standard + tolerance:
            return "High"
        return "Standard"


@dataclass(frozen=True, slots=True)
class BodySegment:
    fat: SegmentMetric
    muscle: SegmentMetric


@dataclass(frozen=True, slots=True)
class Impedance:
    right_arm: float | None
    left_arm: float | None
    trunk: float | None
    right_leg: float | None
    left_leg: float | None


@dataclass(frozen=True, slots=True)
class RenphoReportData:
    report_id: str | None
    measured_at: datetime
    gender: str
    age: int | None
    height_cm: float | None
    body_score: float | None
    weight: ReportMetric
    body_fat_mass: ReportMetric
    bone_mass: ReportMetric
    protein_mass: ReportMetric
    water_mass: ReportMetric
    muscle_mass: ReportMetric
    skeletal_muscle_mass: ReportMetric
    bmi: ReportMetric
    body_fat_percentage: ReportMetric
    optimal_weight: float | None
    weight_control: float | None
    fat_control: float | None
    muscle_control: float | None
    obesity_degree: float | None
    body_type: int | None
    left_arm: BodySegment
    right_arm: BodySegment
    trunk: BodySegment
    left_leg: BodySegment
    right_leg: BodySegment
    impedance_20khz: Impedance
    impedance_100khz: Impedance
    visceral_fat: float | None
    bmr: float | None
    fat_free_mass: float | None
    subcutaneous_fat: float | None
    smi: float | None
    metabolic_age: float | None
    whr: float | None


def normalize_report(raw: dict[str, Any], measured_at: datetime) -> RenphoReportData:
    weight = _number(raw, "weight")
    body_fat_pct = _number(raw, "bodyfat")
    protein_pct = _number(raw, "protein")
    water_pct = _number(raw, "water")
    gender_code = _integer(raw, "gender")
    return RenphoReportData(
        report_id=_text(raw, "reportId"),
        measured_at=measured_at,
        gender={0: "Female", 1: "Male"}.get(gender_code, "Not available")
        if gender_code is not None
        else "Not available",
        age=_integer(raw, "measureAge"),
        height_cm=_number(raw, "height"),
        body_score=_number(raw, "bodyScore"),
        weight=_metric(raw, "weight", "weightMin", "weightMax", "weightStd"),
        body_fat_mass=ReportMetric(
            _mass(weight, body_fat_pct),
            _number(raw, "bfmMin"),
            _number(raw, "bfmMax"),
            _number(raw, "bfmStd"),
        ),
        bone_mass=_metric(raw, "bone", "boneMin", "boneMax"),
        protein_mass=ReportMetric(
            _mass(weight, protein_pct),
            _number(raw, "proteinMassMin"),
            _number(raw, "proteinMassMax"),
        ),
        water_mass=ReportMetric(
            _mass(weight, water_pct),
            _number(raw, "waterMassMin"),
            _number(raw, "waterMassMax"),
        ),
        muscle_mass=_metric(raw, "sinew", "muscleMassMin", "muscleMassMax"),
        skeletal_muscle_mass=_metric(raw, "smmMass", "smmMin", "smmMax", "smmStd"),
        bmi=_metric(raw, "bmi", "bmiMin", "bmiMax", "bmiStd"),
        body_fat_percentage=_metric(raw, "bodyfat", "bfpMin", "bfpMax", "bfpStd"),
        optimal_weight=_number(raw, "weightStd"),
        weight_control=_number(raw, "weightControl"),
        fat_control=_number(raw, "bfmCtrl"),
        muscle_control=_number(raw, "ffmCtrl"),
        obesity_degree=_number(raw, "obesityDegree"),
        body_type=_integer(raw, "bodyType"),
        left_arm=_segment(raw, "la"),
        right_arm=_segment(raw, "ra"),
        trunk=_segment(raw, "t"),
        left_leg=_segment(raw, "ll"),
        right_leg=_segment(raw, "rl"),
        impedance_20khz=_impedance(raw, "z20"),
        impedance_100khz=_impedance(raw, "z100"),
        visceral_fat=_number(raw, "visfat"),
        bmr=_number(raw, "bmr"),
        fat_free_mass=_number(raw, "fatFreeWeight"),
        subcutaneous_fat=_number(raw, "subfat"),
        smi=_number(raw, "smi"),
        metabolic_age=_number(raw, "bodyage"),
        whr=_number(raw, "whr"),
    )


def _metric(
    raw: dict[str, Any], value: str, minimum: str, maximum: str, standard: str = ""
) -> ReportMetric:
    return ReportMetric(
        _number(raw, value),
        _number(raw, minimum),
        _number(raw, maximum),
        _number(raw, standard) if standard else None,
    )


def _segment(raw: dict[str, Any], prefix: str) -> BodySegment:
    return BodySegment(
        SegmentMetric(
            _number(raw, f"{prefix}BodyFatMass"),
            _number(raw, f"{prefix}BodyFatPct"),
            _number(raw, f"{prefix}BodyFatStd"),
        ),
        SegmentMetric(
            _number(raw, f"{prefix}MuscleMass"),
            _number(raw, f"{prefix}Muscle"),
            _number(raw, f"{prefix}MuscleStd"),
        ),
    )


def _impedance(raw: dict[str, Any], prefix: str) -> Impedance:
    return Impedance(
        _number(raw, f"{prefix}HandR"),
        _number(raw, f"{prefix}HandL"),
        _number(raw, f"{prefix}Body"),
        _number(raw, f"{prefix}FootR"),
        _number(raw, f"{prefix}FootL"),
    )


def _mass(weight: float | None, percentage: float | None) -> float | None:
    if weight is None or percentage is None:
        return None
    return round(weight * percentage / 100, 2)


def _number(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(raw: dict[str, Any], key: str) -> int | None:
    value = _number(raw, key)
    return int(value) if value is not None else None


def _text(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    return str(value) if value not in {None, ""} else None
