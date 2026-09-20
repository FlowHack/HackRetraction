"""Тесты генератора gcode: инварианты калибровки и локализация комментариев.

Параметры соответствуют проверенному эталону example_gcode/
(retraction_calibration.gcode): dx=dy=320, srd=0.8, ird=0.1, srs=5.0,
irs=2.0, ps=70.0, tsh=232, tih=0, tb=80, fs=40, fsi=0, nd=0.4, lh=0.2,
fd=1.75, em=0.97, lt=25, nt=15, ts=150.
"""

from __future__ import annotations

import pytest

from hackretraction.engine.generator import (
    FRONT_LABEL,
    GENERATOR_VERSION,
    _e_value,
    generate_gcode,
)
from hackretraction.errors import GenerationError
from hackretraction.i18n import I18N_COMMENTS

ETALON_PARAMS: dict[str, float] = {
    "startRetractiondistance": 0.8,
    "incrementRetractiondistance": 0.1,
    "startRetractionspeed": 5.0,
    "incrementRetractionspeed": 2.0,
    "tempStarthotend": 232.0,
    "tempIncrementhotend": 0.0,
    "tempBed": 80.0,
    "speedFan": 40.0,
    "speedFanIncrement": 0.0,
    "layerHeight": 0.2,
    "printSpeed": 70.0,
    "speedTravel": 150.0,
    "nozzleDiameter": 0.4,
    "filamentDiameter": 1.75,
    "extrusionMultiplier": 0.97,
    "dimensionX": 320.0,
    "dimensionY": 320.0,
    "layersTest": 25.0,
    "NumTests": 15.0,
    "customGcode": "",
}


def _gcode(**overrides: object) -> str:
    params = {**ETALON_PARAMS, **overrides}
    return generate_gcode(params, ";START", ";END")


def test_version_header() -> None:
    gcode = _gcode()
    assert gcode.startswith(";Calibration Generator " + GENERATOR_VERSION + "\n")


def test_start_movement_position() -> None:
    # dx=320 -> xpos = 320/2 - 30 = 130.0, как в эталоне.
    gcode = _gcode()
    assert "G1 F9000 X130.0 Y130.0 Z0.2" in gcode


def test_raft_extrusion_values() -> None:
    # eValue(60)*1.25 = 1.72803 (эталон: G1 F2100 X190.0 Y130.0 E1.72803).
    gcode = _gcode()
    assert "G1 F2100 X190.0 Y130.0 E1.72803" in gcode
    assert "G1 F2100 X130.0 Y131.0 E3.45607" in gcode


def test_calibration_values() -> None:
    # eValue(10) = 0.23040, eValue(1) = 0.02304 (эталон).
    gcode = _gcode()
    assert "G1 F4200 Y10 E0.23040" in gcode
    assert "G1 F4200 X-2 E0.02304" in gcode
    # скорость ретракции первого теста: (5.0 + 2.0*0)*60 = 300.00
    assert "G1 E-0.80 F300.00" in gcode


def test_calibration_geometry() -> None:
    """Число тестов/слоёв и маркеры фаз."""
    gcode = _gcode()
    lines = gcode.splitlines()
    nt, lt = 15, 25
    # по одному G1 Z0.2 на каждый слой теста
    assert sum(1 for l in lines if l == "G1 Z0.2") == nt * lt
    # M106/M104 — по одному на тест
    assert sum(1 for l in lines if l.startswith("M106")) == nt
    assert sum(1 for l in lines if l.startswith("M104")) == nt
    # смена режима относительных координат перед калибровкой
    assert "M83" in lines and "G91" in lines
    # конечный gcode вставлен в конец
    assert gcode.rstrip().endswith(";END")


def test_front_label_printed() -> None:
    """Надпись «перед» печатается на первом слое перед кубом."""
    gcode = _gcode()
    assert "G0 F9000 X-42 Y-25" in gcode
    assert "G0 F9000 X42 Y25" in gcode
    # буквы печатаются штрихами с экструзией
    assert "G1 F4200 X1.0 E0.02304" in gcode


def test_all_inputs_section() -> None:
    gcode = _gcode()
    assert ";All inputs" in gcode
    assert ";Dimension X \t\t\t\t\t320" in gcode
    assert ";Number of Tests                15" in gcode


def test_comments_localization_ru() -> None:
    """Комментарии локализуются, команды остаются неизменными."""
    params = {**ETALON_PARAMS, "customGcode": ""}
    g_en = generate_gcode(params, ";START", ";END")
    g_ru = generate_gcode(params, ";START", ";END", comments=I18N_COMMENTS["ru"])
    assert ";Дистанция ретракции (вид сверху)" in g_ru
    assert ";Все параметры" in g_ru
    assert ";Слой 3" in g_ru
    assert ";ПЕРЕД" in g_ru
    # команды (не-комментарии) должны совпадать
    cmds_en = [l for l in g_en.splitlines() if l and not l.startswith(";")]
    cmds_ru = [l for l in g_ru.splitlines() if l and not l.startswith(";")]
    assert cmds_en == cmds_ru


def test_front_label_constant() -> None:
    assert FRONT_LABEL == "HACKRETRACTION"


def test_e_value_etalon() -> None:
    # eValue(10) = 0.23040 и eValue(1) = 0.02304 из эталона.
    assert abs(_e_value(ETALON_PARAMS, 10) - 0.23040) < 1e-5
    assert abs(_e_value(ETALON_PARAMS, 1) - 0.02304) < 1e-5


def test_invalid_params_raise() -> None:
    with pytest.raises(GenerationError):
        _gcode(NumTests=0)
    with pytest.raises(GenerationError):
        _gcode(layersTest=0)
    with pytest.raises(GenerationError):
        generate_gcode({}, ";", ";")  # type: ignore[arg-type]
