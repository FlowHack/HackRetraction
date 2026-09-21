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
    # dx=320 -> рафт стартует с (320/2-45, 320/2-40) = (115.0, 120.0).
    gcode = _gcode()
    assert "G1 F9000 X115.00 Y120.00 Z0.20" in gcode


def test_raft_extrusion_values() -> None:
    # eValue(90)*1.25 = 2.59205 (первая линия слоя 1, шаг 1 мм)
    gcode = _gcode()
    assert "G1 F2100 X205.00 Y120.00 E2.59205" in gcode
    # вторая линия слоя 1 — Y121 (шаг 1 мм), E накоплен: 2*2.59205
    assert "G1 F2100 X115.00 Y121.00 E5.18410" in gcode


def test_calibration_values() -> None:
    # eValue(10) = 0.23040, eValue(1) = 0.02304 (эталон).
    gcode = _gcode()
    # первое движение печати Right-стороны: от (185,135) на Y+10
    assert "G1 F4200 Y145.00 E0.23040" in gcode
    # маркер нижнего левого угла: от (135,135) на X-2
    assert "G1 F4200 X133.00 E0.02304" in gcode
    # скорость ретракции первого теста: (5.0 + 2.0*0)*60 = 300.00
    assert "G1 E-0.80 F300.00" in gcode


def test_calibration_geometry() -> None:
    """Число тестов/слоёв и маркеры фаз."""
    gcode = _gcode()
    lines = gcode.splitlines()
    nt, lt = 15, 25
    # по одному G1 Z на каждый слой теста + стартовый подъём + 2 слоя текста
    assert sum(1 for l in lines if l.startswith("G1 Z")) == nt * lt + 3
    # M106/M104 — по одному на тест
    assert sum(1 for l in lines if l.startswith("M106")) == nt
    assert sum(1 for l in lines if l.startswith("M104")) == nt
    # абсолютные координаты (G90), относительная экструзия (M83);
    # G91 — только для штрихов букв надписи (2 слоя x 3 периметра = 6 раз)
    assert "M83" in lines and "G90" in lines and lines.count("G91") == 6
    # конечный gcode вставлен в конец
    assert gcode.rstrip().endswith(";END")


def test_front_label_printed() -> None:
    """Надпись печатается выпуклыми линиями поверх сплошной подложки."""
    gcode = _gcode()
    lines = gcode.splitlines()
    # слой 1: зигзаг с шагом 1 мм, G0-переходы между линиями + возврат к слою 2
    i1 = lines.index(";Layer 1")
    i2 = lines.index(";Layer 2")
    g0s = [l for l in lines[i1:i2] if l.startswith("G0")]
    assert len(g0s) == 81 and g0s[0] == "G0 F9000 X205.00 Y121.00"
    i3 = next(
        i for i, l in enumerate(lines[i2:], i2)
        if l.startswith("G0 F9000 X135.00 Y135.00 Z0.60")
    )
    # слой 2: тоже зигзаг с G0-переходами до перехода к старту калибровки
    assert any(l.startswith("G0") for l in lines[i2:i3])
    # переход к тексту (text_x=cx-42=118, text_y=cy-32=128)
    assert "G0 F9000 X118.00 Y128.00" in gcode
    # 3 периметра: смещение старта по X на диаметр сопла (0.4/0.8)
    assert "G0 F9000 X118.40 Y128.00" in gcode
    assert "G0 F9000 X118.80 Y128.00" in gcode
    # первый штрих буквы H: (0,0)->(0,7), Y инвертирован (вверх, Y-),
    # ev = eValue(7) = 0.16128
    assert "G1 F4200 X0.00 Y-7.00 E0.16128" in gcode
    # микро-ретракт между буквами: от конца H (5,7) к началу A (6,0)
    assert "G1 F9000 E-0.50" in gcode
    assert "G0 F9000 X1.00 Y7.00" in gcode
    assert "G1 F9000 E0.50" in gcode
    # прыжок к началу буквы A: pts[0]=(0,7) -> X0.00 Y-7.00
    assert "G0 F9000 X0.00 Y-7.00" in gcode
    # текст печатается на 2 слоях (Z0.60 и Z0.80), затем возврат на Z0.60
    assert "G1 Z0.60" in gcode and "G1 Z0.80" in gcode
    assert "G0 F9000 Z0.60" in gcode


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
