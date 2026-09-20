from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


class ValidationError(ValueError):
    """A measurement contains invalid user input."""


def local_now() -> datetime:
    return datetime.now(BERLIN)


def parse_local_datetime(value: str, *, now: datetime | None = None) -> datetime:
    """Parse an ISO local timestamp and normalize it to Europe/Berlin."""
    if not value.strip():
        return now or local_now()
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValidationError("Use YYYY-MM-DD HH:MM, for example 2026-08-13 08:30") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=BERLIN)
    return parsed.astimezone(BERLIN)


def _bounded(name: str, value: float | int | None, low: float, high: float) -> None:
    if value is not None and not low <= value <= high:
        raise ValidationError(f"{name} must be between {low:g} and {high:g}")


@dataclass(frozen=True, slots=True)
class BodyComposition:
    measured_at: datetime
    weight: float
    percent_fat: float | None = None
    bmi: float | None = None
    percent_hydration: float | None = None
    muscle_mass: float | None = None
    bone_mass: float | None = None
    visceral_fat_rating: float | None = None
    basal_met: float | None = None
    metabolic_age: float | None = None

    def __post_init__(self) -> None:
        if self.measured_at.tzinfo is None:
            raise ValidationError("Measurement time must include a timezone")
        _bounded("weight", self.weight, 20, 400)
        _bounded("percent fat", self.percent_fat, 1, 75)
        _bounded("BMI", self.bmi, 5, 100)
        _bounded("percent hydration", self.percent_hydration, 1, 80)
        _bounded("muscle mass", self.muscle_mass, 1, 250)
        _bounded("bone mass", self.bone_mass, 0.1, 30)
        _bounded("visceral fat rating", self.visceral_fat_rating, 1, 59)
        _bounded("basal metabolism", self.basal_met, 300, 10000)
        _bounded("metabolic age", self.metabolic_age, 1, 150)

    def garmin_kwargs(self) -> dict[str, Any]:
        """Map validated fields for upload, excluding Garmin's corrupted metabolic-age import."""
        return {
            "timestamp": self.measured_at.isoformat(),
            "weight": self.weight,
            "percent_fat": self.percent_fat,
            "bmi": self.bmi,
            "percent_hydration": self.percent_hydration,
            "muscle_mass": self.muscle_mass,
            "bone_mass": self.bone_mass,
            "visceral_fat_rating": self.visceral_fat_rating,
            "basal_met": self.basal_met,
            # Garmin Connect currently corrupts this valid FIT field during import.
            # Keep it in the local model/preview, but do not upload it.
            "metabolic_age": None,
        }

    def summary(self) -> list[tuple[str, str]]:
        """Format present body-composition values with units for upload confirmation."""
        labels = {
            "weight": "Weight",
            "percent_fat": "Body fat",
            "bmi": "BMI",
            "percent_hydration": "Hydration",
            "muscle_mass": "Muscle mass",
            "bone_mass": "Bone mass",
            "visceral_fat_rating": "Visceral fat rating",
            "basal_met": "Basal metabolism",
            "metabolic_age": "Metabolic age",
        }
        units = {
            "weight": " kg",
            "percent_fat": "%",
            "percent_hydration": "%",
            "muscle_mass": " kg",
            "bone_mass": " kg",
            "basal_met": " kcal",
            "metabolic_age": " years",
        }
        result = [("Measured at", self.measured_at.isoformat(timespec="minutes"))]
        for field in fields(self):
            if field.name == "measured_at":
                continue
            value = getattr(self, field.name)
            if value is not None:
                result.append((labels[field.name], f"{value:g}{units.get(field.name, '')}"))
        return result


@dataclass(frozen=True, slots=True)
class BloodPressure:
    measured_at: datetime
    systolic: int
    diastolic: int
    pulse: int
    notes: str = ""

    def __post_init__(self) -> None:
        if self.measured_at.tzinfo is None:
            raise ValidationError("Measurement time must include a timezone")
        _bounded("systolic", self.systolic, 70, 260)
        _bounded("diastolic", self.diastolic, 40, 150)
        _bounded("pulse", self.pulse, 20, 250)
        if self.diastolic >= self.systolic:
            raise ValidationError("Diastolic pressure must be lower than systolic pressure")
        if len(self.notes) > 500:
            raise ValidationError("Notes must be at most 500 characters")

    def summary(self) -> list[tuple[str, str]]:
        """Build confirmation labels while preserving the user's optional measurement note."""
        result = [
            ("Measured at", self.measured_at.isoformat(timespec="minutes")),
            ("Blood pressure", f"{self.systolic}/{self.diastolic} mmHg"),
            ("Pulse", f"{self.pulse} bpm"),
        ]
        if self.notes:
            result.append(("Notes", self.notes))
        return result
