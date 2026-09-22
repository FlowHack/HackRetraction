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
}


def _gcode(**overrides: object) -> str:
    params = {**ETALON_PARAMS, **overrides}
    return generate_gcode(params, ";START", ";END")


def test_version_header() -> None:
    gcode = _gcode()
    assert gcode.startswith(";Calibration Generator " + GENERATOR_VERSION + "\n")


def test_start_movement_position() -> None:
    # dx=320 -> рафт стартует с (320/2-30, 320/2-38) = (130.0, 122.0).
    gcode = _gcode()
    assert "G1 F9000 X130.00 Y122.00 Z0.20" in gcode
    # абсолютная экструзия для подложки: M82 + сброс счётчика до рафта
    assert "M82 ; Включаем абсолютную экструзию для подложки" in gcode
    assert "G92 E0 ; Сбрасываем счетчик экструдера" in gcode
    assert gcode.index("M82") < gcode.index(";Layer 1")


def test_raft_extrusion_values() -> None:
    # eValue(60)*1.25 = 1.72803 (первая линия слоя 1, шаг 1 мм)
    gcode = _gcode()
    assert "G1 F2100 X190.00 Y122.00 E1.72803" in gcode
    # рабочий переход по краю слоя 1: 1 мм вдоль Y, eValue(1)*1.25 = 0.0288
    assert "G1 F2100 X190.00 Y123.00 E1.75683" in gcode
    # вторая линия слоя 1 — Y123 (шаг 1 мм), E накоплен: 1.72803+0.0288+1.72803
    assert "G1 F2100 X130.00 Y123.00 E3.48487" in gcode


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
    # по одному G1 Z на каждый слой башни + стартовый подъём (G1 Z2);
    # переходы между фазами — G0 Z (рафт->буквы, подложка->буквы, подложка->башня)
    assert sum(1 for l in lines if l.startswith("G1 Z")) == nt * lt + 1
    # M106/M104 — по одному на тест
    assert sum(1 for l in lines if l.startswith("M106")) == nt
    assert sum(1 for l in lines if l.startswith("M104")) == nt
    # абсолютные координаты (G90), относительная экструзия (M83);
    # G91 больше не используется — текст строится в абсолютных координатах
    assert "M83" in lines and "G90" in lines and lines.count("G91") == 0
    # конечный gcode вставлен в конец
    assert gcode.rstrip().endswith(";END")


def test_front_label_printed() -> None:
    """Надпись печатается выпуклыми линиями поверх сплошной подложки."""
    gcode = _gcode()
    lines = gcode.splitlines()
    # слой 1: зигзаг с шагом 1 мм, переходы по краю — рабочие G1 с экструзией;
    # единственный G0 — переезд на 2-й слой (с Z), холостых зигзаг-переходов нет
    i1 = lines.index(";Layer 1")
    i2 = lines.index(";Layer 2")
    g0_zigzag = [l for l in lines[i1:i2] if l.startswith("G0") and "Z" not in l]
    assert len(g0_zigzag) == 0
    # слой 2: переходы по краю — тоже рабочие G1, холостых G0 нет
    i3 = next(
        i for i, l in enumerate(lines[i2:], i2)
        if l.startswith("G0 F9000 X130.60 Y129.00")
    )
    assert not any(l.startswith("G0") for l in lines[i2:i3])
    # первый штрих буквы H: (0,0)->(0,7) с масштабом 0.7 -> (0,0)->(0,4.9),
    # Y инвертирован (вверх, Y-), offset = nd/2 = 0.2;
    # наружный контур X130.8, внутренний X130.4
    assert "G0 F9000 X130.80 Y129.00" in gcode
    # U-петля: вниз по наружному контуру (dist 4.9 -> E0.11290),
    # поперёк (dist 0.4 -> E0.00922), вверх по внутреннему;
    # скорость периметра — 50% от основной (ps=70 -> F2100)
    assert "G1 F2100 X130.80 Y124.10 E0.11290" in gcode
    assert "G1 F2100 X130.40 Y124.10 E0.00922" in gcode
    assert "G1 F2100 X130.40 Y129.00 E0.11290" in gcode
    # ретракт между штрихами буквы — параметризованный (srd=0.8, srs=5.0)
    assert "G1 F300 E-0.80" in gcode
    assert "G1 F300 E0.80" in gcode
    # второй штрих H: (0,3.5)->(5,3.5) с масштабом 0.7 -> (0,2.45)->(3.5,2.45)
    # -> abs (130.6,126.55)->(134.1,126.55), наружный контур Y126.75, внутренний Y126.35
    assert "G0 F9000 X130.60 Y126.75" in gcode
    assert "G1 F2100 X134.10 Y126.75 E0.08064" in gcode
    # старые смещения стартовой точки больше не используются
    assert "G0 F9000 X118.40 Y127.60" not in gcode
    assert "G0 F9000 X118.40 Y128.00" not in gcode
    assert "G0 F9000 X118.00 Y127.60" not in gcode
    # текст печатается на 2 слоях (Z0.60 и Z0.80), переходы — G0 Z
    assert "G0 F9000 Z0.60" in gcode and "G0 F9000 Z0.80" in gcode
    # локальная подложка под башней: 2 слоя, область [130,190]x[130,190]
    assert ";Layer 3 (local raft)" in gcode
    assert ";Layer 4 (local raft)" in gcode
    # башня стартует с Z=1.00 (5*lh), слой 5; переход — СНАЧАЛА XY, ЗАТЕМ Z
    i_xy = lines.index("G0 F9000 X135.00 Y135.00")
    i_z = lines.index("G0 F9000 Z1.00")
    assert i_xy < i_z
    assert ";Layer 5" in gcode


def test_all_inputs_section() -> None:
    gcode = _gcode()
    assert ";All inputs" in gcode
    assert ";Dimension X \t\t\t\t\t320" in gcode
    assert ";Number of Tests                15" in gcode


def test_comments_localization_ru() -> None:
    """Комментарии локализуются, команды остаются неизменными."""
    params = {**ETALON_PARAMS}
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
