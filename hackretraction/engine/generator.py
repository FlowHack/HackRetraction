"""Генератор gcode калибровочного куба ретракции.

Логика перенесена БЕЗ ИЗМЕНЕНИЙ из fork/RetCalMain.py (версия 1.3.1).
Отличия от оригинала:
- стартовый и конечный gcode берутся из профиля принтера (или дефолтов),
  а не зашиты жёстко;
- таблица "Variables by Height" идёт от 0 до nt-1 (консистентно с кодом
  калибровки, в оригинале — в обратном порядке);
- на первом слое перед кубом печатается надпись FRONT_LABEL («HACKRETRACTION»)
  точечным шрифтом 5x7 — ориентация куба (в оригинале перед не помечался).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from ..errors import GenerationError
from ..logging import _LOGGER
from .comments import EN_DEFAULT_COMMENTS

GENERATOR_VERSION = "1.3.1"


def _fmt(value: float, digits: int) -> str:
    """Форматирование как в оригинале: round(Decimal(value), digits)."""
    return str(round(Decimal(value), digits))


def _e_value(params: Dict[str, float], extrusion_length: float) -> float:
    """E-значение (формула 1.3.1: /em*1.25, без +.07539 из Flask-версии)."""
    nd = float(params["nozzleDiameter"])
    lh = float(params["layerHeight"])
    fd = float(params["filamentDiameter"])
    em = float(params["extrusionMultiplier"])
    area = (nd - lh) * lh + 3.14159 * (lh / 2) ** 2
    return (area * extrusion_length * 4) / (3.14159 * fd**2 / em * 1.25)


def _side(
    lines: List[str],
    params: Dict[str, float],
    base: int,
    move_axis: str,
    move_sign: int,
    retract_axis: str,
    retract_sign: int,
    test: int,
    ev: float,
    ps: float,
    ts: float,
) -> None:
    """Одна сторона куба: 4 значения втягивания (паттерн оригинала 1.3.1).

    Движение печати идёт по move_axis, отъезд/приезд при втягивании —
    по retract_axis (в оригинале оси разные для каждой стороны).
    """
    srd = float(params["startRetractiondistance"])
    ird = float(params["incrementRetractiondistance"])
    srs = float(params["startRetractionspeed"])
    irs = float(params["incrementRetractionspeed"])
    speed = (srs + irs * test) * 60
    lines.append(f"G1 F{int(ps * 60)} {move_axis}{move_sign * 10} E{_fmt(ev, 5)}")
    for i in range(4):
        value = srd + ird * (base + i)
        lines.append(f"G1 E{_fmt(-value, 2)} F{_fmt(speed, 2)}")
        lines.append(f"G0 F{int(ts) * 60} {retract_axis}{retract_sign * 10}")
        lines.append(f"G0 F{int(ts) * 60} {retract_axis}{-retract_sign * 10}")
        lines.append(f"G1 E{_fmt(value, 2)} F{_fmt(speed, 2)}")
        lines.append(f"G1 F{int(ps) * 60} {move_axis}{move_sign * 10} E{_fmt(ev, 5)}")


def _corner_markers(
    lines: List[str],
    ps: float,
    marker: float,
    size: int,
    sx1: int,
    sy1: int,
    sx2: int,
    sy2: int,
) -> None:
    """Маркеры углов слоя (паттерн оригинала: X-2/Y-2/X2/Y2 и т.д.)."""
    lines.append(f"G1 F{int(ps * 60)} X{sx1 * size} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} Y{sy1 * size} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} X{sx2 * size} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} Y{sy2 * size} E{_fmt(marker, 5)}")


# Точечный шрифт 5x7 (бит 4..0 = колонки 0..4, 7 строк сверху вниз).
_FONT_5X7 = {
    "H": (17, 17, 17, 31, 17, 17, 17),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "K": (17, 17, 19, 30, 20, 17, 17),
    "R": (30, 17, 17, 30, 20, 17, 17),
    "E": (30, 17, 16, 30, 16, 17, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "N": (17, 25, 21, 19, 17, 17, 17),
}

FRONT_LABEL = "HACKRETRACTION"
_FRONT_LABEL_X = -42  # старт надписи относительно центра калибровки
_FRONT_LABEL_Y = -25  # перед кубом (Y-), вне зоны ретракций


def _print_text(
    lines: List[str],
    ps: float,
    ts: float,
    marker: float,
    text: str,
    x: float,
    y: float,
    step: float = 1.0,
) -> None:
    """Печать текста точечным шрифтом 5x7 в относительных координатах.

    Каждая точка — короткий штрих с экструзией (как маркеры углов).
    После печати позиция возвращается в исходную точку.
    """
    lines.append(f"G0 F{int(ts) * 60} X{x} Y{y}")
    for ch in text.upper():
        glyph = _FONT_5X7.get(ch)
        if glyph is None:
            lines.append(f"G0 F{int(ts) * 60} X{step * 6}")
            continue
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits & (1 << (4 - col)):
                    lines.append(f"G1 F{int(ps * 60)} X{step} E{_fmt(marker, 5)}")
                    lines.append(f"G0 F{int(ts) * 60} X{-step}")
                lines.append(f"G0 F{int(ts) * 60} X{step}")
            lines.append(f"G0 F{int(ts) * 60} X{-step * 5} Y{step}")
        lines.append(f"G0 F{int(ts) * 60} Y{-step * 7}")
        lines.append(f"G0 F{int(ts) * 60} X{step * 6}")
    lines.append(f"G0 F{int(ts) * 60} X{-x} Y{-y}")


def generate_gcode(
    params: Dict[str, float],
    start_gcode: str,
    end_gcode: str,
    comments: Dict[str, str] | None = None,
) -> str:
    """Генерация полного gcode калибровочного куба.

    Аргументы:
        params: словарь параметров (ключи как в DEFAULT_PARAMS).
        start_gcode: стартовый gcode принтера (уже с подставленными
            плейсхолдерами) или пустая строка.
        end_gcode: конечный gcode принтера (уже с подставленными
            плейсхолдерами) или пустая строка.
        comments: локализованные комментарии gcode (ключи как в
            EN_DEFAULT_COMMENTS). Если None — английские.

    Возвращает полный текст gcode (с финальным переводом строки).
    """
    _c = EN_DEFAULT_COMMENTS if comments is None else {**EN_DEFAULT_COMMENTS, **comments}
    try:
        nt = int(float(params["NumTests"]))
        lt = int(float(params["layersTest"]))
        if nt < 1 or lt < 1:
            raise GenerationError("Число тестов и слоёв должно быть не меньше 1")
    except (KeyError, TypeError, ValueError) as exc:
        raise GenerationError(f"Некорректные параметры: {exc}") from exc

    srd = float(params["startRetractiondistance"])
    ird = float(params["incrementRetractiondistance"])
    srs = float(params["startRetractionspeed"])
    irs = float(params["incrementRetractionspeed"])
    tsh = float(params["tempStarthotend"])
    tih = float(params["tempIncrementhotend"])
    fs = float(params["speedFan"])
    fsi = float(params["speedFanIncrement"])
    lh = float(params["layerHeight"])
    ts = float(params["speedTravel"])
    dx = float(params["dimensionX"])
    dy = float(params["dimensionY"])
    ps = float(params["printSpeed"])
    nd = float(params["nozzleDiameter"])
    fd = float(params["filamentDiameter"])
    em = float(params["extrusionMultiplier"])
    custom_gcode = str(params.get("customGcode", "")).strip()

    lines: List[str] = []

    # --- Заголовок-схема (вид сверху) ---
    lines.append(";Calibration Generator " + GENERATOR_VERSION)
    lines.append(";")
    lines.append(";")
    lines.append(";" + _c["header_retraction"])
    lines.append(";")
    lines.append(
        f";       {_fmt(srd + ird * 11, 2)}    {_fmt(srd + ird * 10, 2)}"
        f"    {_fmt(srd + ird * 9, 2)}    {_fmt(srd + ird * 8, 2)}"
    )
    lines.append(";\t\t|\t\t|\t\t|\t\t|")
    lines.append(";")
    lines.append(f";{_fmt(srd + ird * 12, 2)}-                               -{_fmt(srd + ird * 7, 2)}")
    lines.append(";")
    lines.append(";")
    lines.append(f";{_fmt(srd + ird * 13, 2)}-                               -{_fmt(srd + ird * 6, 2)}")
    lines.append(";")
    lines.append(";")
    lines.append(f";{_fmt(srd + ird * 14, 2)}-                               -{_fmt(srd + ird * 5, 2)}")
    lines.append(";")
    lines.append(";")
    lines.append(f";{_fmt(srd + ird * 15, 2)}-                               -{_fmt(srd + ird * 4, 2)}")
    lines.append(";")
    lines.append(";\t\t|\t\t|\t\t|\t\t|")
    lines.append(
        f";       {_fmt(srd + ird * 0, 2)}    {_fmt(srd + ird * 1, 2)}"
        f"    {_fmt(srd + ird * 2, 2)}    {_fmt(srd + ird * 3, 2)}"
    )
    lines.append(";")
    lines.append(";" + _c["front"])
    lines.append(";")

    # --- Таблица переменных по высоте (от 0 до nt-1, консистентно с кодом) ---
    lines.append(";" + _c["variables_by_height"])
    lines.append(";")
    lines.append(
        f";{_c['table_height']:<12} {_c['table_retr_speed']:<15}"
        f" {_c['table_nozzle_temp']:<11} {_c['table_fan_speed']}"
    )
    lines.append(";")
    for test in range(nt):
        lines.append(
            f";{lt} layers      {_fmt(srs + irs * test, 2)}"
            f"      {_fmt(tsh + tih * test, 2)}"
            f"      {_fmt(fs + fsi * test, 2)}"
        )

    # --- All inputs ---
    lines.append(";")
    lines.append(";")
    lines.append(";" + _c["all_inputs"])
    lines.append(";")
    lines.append(f";{_c['dim_x']} \t\t\t\t\t{int(dx)}")
    lines.append(f";{_c['dim_y']} \t\t\t\t\t{int(dy)}")
    lines.append(f";{_c['start_retr_dist']}\t{srd}")
    lines.append(f";{_c['inc_retr']} \t\t\t{ird}")
    lines.append(f";{_c['start_retr_speed']} \t\t{srs}")
    lines.append(f";{_c['retr_speed_inc']} \t{irs}")
    lines.append(f";{_c['print_speed']} \t\t\t\t\t{ps}")
    lines.append(f";{_c['start_temp']} \t\t\t\t\t{int(tsh)}")
    lines.append(f";{_c['inc_temp']} \t\t\t\t{int(tih)}")
    lines.append(f";{_c['bed_temp']} \t\t\t\t\t\t{int(float(params['tempBed']))}")
    lines.append(f";{_c['fan_speed']} \t\t\t\t\t\t{int(fs)}")
    lines.append(f";{_c['fan_speed_inc']} \t\t\t{int(fsi)}")
    lines.append(f";{_c['nozzle_diameter']} \t\t\t\t{nd}")
    lines.append(f";{_c['layer_height']} \t\t\t\t\t{lh}")
    lines.append(f";{_c['filament_diameter']} \t\t\t\t{fd}")
    lines.append(f";{_c['extrusion_mult']} \t\t\t{em}")
    lines.append(f";{_c['layers_per_test']}                {lt}")
    lines.append(f";{_c['num_tests']}                {nt}")
    lines.append(";")
    lines.append(";")

    # --- Start Gcode (из профиля принтера или дефолт) + пользовательский ---
    lines.append(";" + _c["start_gcode"])
    if start_gcode:
        lines.append(start_gcode.strip())
    if custom_gcode:
        lines.append(custom_gcode)
    lines.append(";")
    lines.append(";")

    # --- Start Movement ---
    xpos = dx / 2 - 30
    ypos = dy / 2 - 30
    zpos = lh
    lines.append(";" + _c["start_movement"])
    lines.append(";")
    lines.append("G1 Z2")
    lines.append(f"G1 F{int(ts) * 60} X{xpos} Y{ypos} Z{zpos}")
    lines.append(";")

    # --- Рафт (переэкструзия) ---
    ev = _e_value(params, 60) * 1.25
    ev_increase = ev
    remx = xpos
    remy = ypos

    lines.append(";" + _c["layer"] + " 1")
    # Горизонталь
    for _ in range(30):
        lines.append(f"G1 F{int(ps * 60 / 2)} X{xpos + 60} Y{ypos} E{_fmt(ev, 5)}")
        xpos = xpos + 60
        ev = ev + ev_increase
        lines.append(f"G0 F{int(ts) * 60} X{xpos} Y{ypos + 1}")
        ypos = ypos + 1
        lines.append(f"G1 F{int(ps * 60 / 2)} X{xpos - 60} Y{ypos} E{_fmt(ev, 5)}")
        xpos = xpos - 60
        ev = ev + ev_increase
        lines.append(f"G0 F{int(ts) * 60} X{xpos} Y{ypos + 1}")
        ypos = ypos + 1
    # Возврат к началу рафта
    lines.append(f"G0 F{int(ts) * 60} X{xpos} Y{ypos} Z{_fmt(lh * 3, 2)}")
    lines.append(f"G0 F{int(ts) * 60} X{remx} Y{remy} Z{lh + lh}")
    xpos = remx
    ypos = remy

    lines.append(";" + _c["layer"] + " 2")
    # Вертикаль
    for _ in range(30):
        lines.append(f"G1 F{int(ps * 60 / 2)} X{xpos} Y{ypos + 60} E{_fmt(ev, 5)}")
        ypos = ypos + 60
        ev = ev + ev_increase
        lines.append(f"G0 F{int(ts) * 60} X{xpos + 1} Y{ypos}")
        xpos = xpos + 1
        lines.append(f"G1 F{int(ps * 60 / 2)} X{xpos} Y{ypos - 60} E{_fmt(ev, 5)}")
        ypos = ypos - 60
        ev = ev + ev_increase
        lines.append(f"G0 F{int(ts) * 60} X{xpos + 1} Y{ypos}")
        xpos = xpos + 1
    # Возврат к стартовой позиции калибровки
    lines.append(f"G0 F{int(ts) * 60} X{remx + 5} Y{remy + 5} Z{_fmt(lh * 3, 2)}")

    # Относительные перемещения
    lines.append("M83")
    lines.append("G91")

    # --- Калибровка ---
    ev = _e_value(params, 10)
    corenermarker = _e_value(params, 1)
    loopbigcount = 0
    layer = 3
    inner_layers = lt - 1

    for _ in range(nt):
        # Вентилятор и температура на каждый тест
        lines.append(f"M106 S{_fmt((fs + fsi * loopbigcount) * 255 / 100, 0)}")
        lines.append(f"M104 S{_fmt(tsh + tih * loopbigcount, 0)}")
        lines.append(f";{_c['layer']} {layer}")

        # Надпись «перед» — только на первом слое
        if loopbigcount == 0:
            _print_text(
                lines, ps, ts, corenermarker, FRONT_LABEL,
                _FRONT_LABEL_X, _FRONT_LABEL_Y,
            )

        # Маркер угла: нижний левый
        _corner_markers(lines, ps, corenermarker, 2, -1, -1, 1, 1)

        # Bottom (перед): значения 0..3 (движение X+, втягивание Y-)
        _side(lines, params, 0, "X", 1, "Y", -1, loopbigcount, ev, ps, ts)

        # Маркер угла: нижний правый
        _corner_markers(lines, ps, corenermarker, 1, 1, -1, -1, 1)

        # Right: значения 4..7 (движение Y+, втягивание X+)
        _side(lines, params, 4, "Y", 1, "X", 1, loopbigcount, ev, ps, ts)

        # Маркер угла: верхний правый
        _corner_markers(lines, ps, corenermarker, 1, 1, 1, -1, -1)

        # Top (зад): значения 8..11 (движение X-, втягивание Y+)
        _side(lines, params, 8, "X", -1, "Y", 1, loopbigcount, ev, ps, ts)

        # Маркер угла: верхний левый
        _corner_markers(lines, ps, corenermarker, 1, -1, 1, 1, -1)

        # Left: значения 12..15 (движение Y-, втягивание X-)
        _side(lines, params, 12, "Y", -1, "X", -1, loopbigcount, ev, ps, ts)

        # Подъём на высоту слоя
        lines.append(f"G1 Z{lh}")
        layer = layer + 1

        # Внутренние слои теста (без маркеров углов)
        for _ in range(inner_layers):
            lines.append(f";{_c['layer']} {layer}")
            _side(lines, params, 0, "X", 1, "Y", -1, loopbigcount, ev, ps, ts)
            _side(lines, params, 4, "Y", 1, "X", 1, loopbigcount, ev, ps, ts)
            _side(lines, params, 8, "X", -1, "Y", 1, loopbigcount, ev, ps, ts)
            _side(lines, params, 12, "Y", -1, "X", -1, loopbigcount, ev, ps, ts)
            lines.append(f"G1 Z{lh}")
            layer = layer + 1

        loopbigcount = loopbigcount + 1

    # --- End Game (из профиля принтера или дефолт) ---
    if end_gcode:
        lines.append(end_gcode.strip())

    return "\n".join(lines) + "\n"