from datetime import datetime

from garmin_sync.models import BERLIN
from garmin_sync.renpho_report import normalize_report


def test_full_report_mapping() -> None:
    measured_at = datetime(2026, 8, 15, 7, 32, tzinfo=BERLIN)
    raw = {
        "reportId": "P26081502",
        "gender": 1,
        "measureAge": 37,
        "height": 186,
        "bodyScore": 84,
        "weight": 90.85,
        "weightMin": 64.7,
        "weightMax": 87.5,
        "weightStd": 76.1,
        "bodyfat": 18.5,
        "bfmMin": 9.1,
        "bfmMax": 18.2,
        "bone": 5,
        "protein": 16.3,
        "water": 59.7,
        "sinew": 69.05,
        "smmMass": 42.61,
        "bmi": 26.3,
        "bfpMin": 10,
        "bfpMax": 20,
        "weightControl": -5.4,
        "bfmCtrl": -5.4,
        "ffmCtrl": 0,
        "obesityDegree": 119,
        "bodyType": 7,
        "laBodyFatMass": 0.92,
        "laBodyFatPct": 124.3,
        "laBodyFatStd": 0.74,
        "laMuscleMass": 4.3,
        "laMuscle": 113.2,
        "laMuscleStd": 3.8,
        "z20HandR": 259.8,
        "z100HandR": 228.3,
        "visfat": 5,
        "bmr": 1969,
        "fatFreeWeight": 74.04,
        "subfat": 13.3,
        "smi": 9.6,
        "bodyage": 35,
        "whr": 0.88,
    }
    report = normalize_report(raw, measured_at)

    assert report.report_id == "P26081502"
    assert report.gender == "Male"
    assert report.age == 37
    assert report.body_fat_mass.value == 16.81
    assert report.protein_mass.value == 14.81
    assert report.water_mass.value == 54.24
    assert report.optimal_weight == 76.1
    assert report.left_arm.fat.mass == 0.92
    assert report.left_arm.muscle.percentage == 113.2
    assert report.impedance_20khz.right_arm == 259.8
    assert report.impedance_100khz.right_arm == 228.3
    assert report.visceral_fat == 5
    assert report.whr == 0.88


def test_missing_report_fields_remain_unavailable() -> None:
    report = normalize_report({}, datetime(2026, 8, 15, tzinfo=BERLIN))
    assert report.report_id is None
    assert report.gender == "Not available"
    assert report.body_score is None
    assert report.left_leg.fat.mass is None
    assert report.impedance_100khz.trunk is None
