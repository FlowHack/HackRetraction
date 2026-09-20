"""Генератор gcode калибровочного куба ретракции.

Логика перенесена из fork/RetCalMain.py (версия 1.3.1) с существенными
изменениями:
- стартовый и конечный gcode берутся из профиля принтера (или дефолтов),
  а не зашиты жёстко;
- таблица "Variables by Height" идёт от 0 до nt-1 (консистентно с кодом
  калибровки, в оригинале — в обратном порядке);
- на первом слое перед кубом печатается надпись FRONT_LABEL («HACKRETRACTION»)
  точечным шрифтом 5x7 — ориентация куба (в оригинале перед не помечался);
- ВСЕ перемещения — в АБСОЛЮТНЫХ координатах (G90): слайсеры корректно
  отображают превью только без G91. Подложка, надпись и башня центрируются
  относительно стола и никогда не разъезжаются;
- подложка — прямоугольник 90x80 с выступом спереди (Y-) под надпись:
  надпись печатается В выступе подложки, а не отдельно от неё.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Tuple

from ..errors import GenerationError
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
    x: float,
    y: float,
) -> Tuple[float, float]:
    """Одна сторона куба: 4 значения втягивания (паттерн оригинала 1.3.1).

    Движение печати идёт по move_axis, отъезд/приезд при втягивании —
    по retract_axis (в оригинале оси разные для каждой стороны).
    Все координаты — абсолютные (G90). Возвращает (x, y) после печати.
    """
    srd = float(params["startRetractiondistance"])
    ird = float(params["incrementRetractiondistance"])
    srs = float(params["startRetractionspeed"])
    irs = float(params["incrementRetractionspeed"])
    speed = (srs + irs * test) * 60
    # Движение печати на 10 мм по move_axis
    if move_axis == "X":
        x += move_sign * 10
        lines.append(f"G1 F{int(ps * 60)} X{_fmt(x, 2)} E{_fmt(ev, 5)}")
    else:
        y += move_sign * 10
        lines.append(f"G1 F{int(ps * 60)} Y{_fmt(y, 2)} E{_fmt(ev, 5)}")
    for i in range(4):
        value = srd + ird * (base + i)
        lines.append(f"G1 E{_fmt(-value, 2)} F{_fmt(speed, 2)}")
        # Отъезд на 10 мм по retract_axis и возврат
        if retract_axis == "X":
            x += retract_sign * 10
            lines.append(f"G0 F{int(ts) * 60} X{_fmt(x, 2)}")
            x -= retract_sign * 10
            lines.append(f"G0 F{int(ts) * 60} X{_fmt(x, 2)}")
        else:
            y += retract_sign * 10
            lines.append(f"G0 F{int(ts) * 60} Y{_fmt(y, 2)}")
            y -= retract_sign * 10
            lines.append(f"G0 F{int(ts) * 60} Y{_fmt(y, 2)}")
        lines.append(f"G1 E{_fmt(value, 2)} F{_fmt(speed, 2)}")
        # Движение печати на 10 мм по move_axis
        if move_axis == "X":
            x += move_sign * 10
            lines.append(f"G1 F{int(ps * 60)} X{_fmt(x, 2)} E{_fmt(ev, 5)}")
        else:
            y += move_sign * 10
            lines.append(f"G1 F{int(ps * 60)} Y{_fmt(y, 2)} E{_fmt(ev, 5)}")
    return x, y


def _corner_markers(
    lines: List[str],
    ps: float,
    marker: float,
    size: int,
    sx1: int,
    sy1: int,
    sx2: int,
    sy2: int,
    x: float,
    y: float,
) -> Tuple[float, float]:
    """Маркеры углов слоя (паттерн оригинала: X-2/Y-2/X2/Y2 и т.д.).

    Абсолютные координаты. Возвращает (x, y) — позиция не меняется.
    """
    lines.append(f"G1 F{int(ps * 60)} X{_fmt(x + sx1 * size, 2)} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} Y{_fmt(y + sy1 * size, 2)} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} X{_fmt(x + sx2 * size, 2)} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} Y{_fmt(y + sy2 * size, 2)} E{_fmt(marker, 5)}")
    return x, y


# Точечный шрифт 5x7 (бит 4..0 = колонки 0..4, 7 строк сверху вниз).
_FONT_5X7 = {
    "H": (17, 17, 17, 31, 17, 17, 17),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "K": (17, 17, 19, 30, 20, 17, 17),
    "R": (30, 17, 17, 30, 17, 17, 17),
    "E": (30, 17, 16, 30, 16, 17, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "N": (17, 25, 21, 19, 17, 17, 17),
}

FRONT_LABEL = "HACKRETRACTION"


def _print_text(
    lines: List[str],
    ps: float,
    ts: float,
    marker: float,
    text: str,
    x: float,
    y: float,
    step: float = 1.0,
) -> Tuple[float, float]:
    """Печать текста точечным шрифтом 5x7 в АБСОЛЮТНЫХ координатах.

    (x, y) — верхний левый угол текста; текст печатается вниз (Y+).
    Каждая точка — короткий штрих с экструзией (как маркеры углов).
    Возвращает (x, y) — стартовую позицию (перемещение к следующему
    блоку выполняет вызывающий код).
    """
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(x, 2)} Y{_fmt(y, 2)}")
    cx, cy = x, y
    for ch in text.upper():
        glyph = _FONT_5X7.get(ch)
        if glyph is None:
            cx += step * 6
            lines.append(f"G0 F{int(ts) * 60} X{_fmt(cx, 2)}")
            continue
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits & (1 << (4 - col)):
                    cx += step
                    lines.append(f"G1 F{int(ps * 60)} X{_fmt(cx, 2)} E{_fmt(marker, 5)}")
                    cx -= step
                    lines.append(f"G0 F{int(ts) * 60} X{_fmt(cx, 2)}")
                cx += step
                lines.append(f"G0 F{int(ts) * 60} X{_fmt(cx, 2)}")
            cx -= step * 5
            cy += step
            lines.append(f"G0 F{int(ts) * 60} X{_fmt(cx, 2)} Y{_fmt(cy, 2)}")
        cy -= step * 7
        lines.append(f"G0 F{int(ts) * 60} Y{_fmt(cy, 2)}")
        cx += step * 6
        lines.append(f"G0 F{int(ts) * 60} X{_fmt(cx, 2)}")
    return x, y


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
    # Таблица идёт сверху вниз (первая строка — верхний блок башни), чтобы
    # читалась как «Variables by Height»: верх башни = максимальное значение.
    for test in range(nt - 1, -1, -1):
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

    # --- Start Movement (абсолютные координаты, G90) ---
    cx = dx / 2
    cy = dy / 2
    raft_x0 = cx - 45
    raft_y0 = cy - 40
    raft_x1 = cx + 45
    raft_y1 = cy + 40
    tower_x = cx - 20
    tower_y = cy - 20
    text_x = cx - 42
    text_y = cy - 32
    lines.append(";" + _c["start_movement"])
    lines.append(";")
    lines.append("G90")
    lines.append("G1 Z2")
    lines.append(f"G1 F{int(ts) * 60} X{_fmt(raft_x0, 2)} Y{_fmt(raft_y0, 2)} Z{_fmt(lh, 2)}")
    lines.append(";")

    # --- Рафт (переэкструзия): подложка 90x80 с выступом спереди под надпись ---
    ev = _e_value(params, 60) * 1.25
    ev_increase = ev

    lines.append(";" + _c["layer"] + " 1")
    # Горизонталь (зигзаг, шаг 2 мм)
    y = raft_y0
    while y < raft_y1:
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(raft_x1, 2)} Y{_fmt(y, 2)} E{_fmt(ev, 5)}")
        ev = ev + ev_increase
        y = y + 1
        lines.append(f"G0 F{int(ts) * 60} X{_fmt(raft_x1, 2)} Y{_fmt(y, 2)}")
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(raft_x0, 2)} Y{_fmt(y, 2)} E{_fmt(ev, 5)}")
        ev = ev + ev_increase
        y = y + 1
        lines.append(f"G0 F{int(ts) * 60} X{_fmt(raft_x0, 2)} Y{_fmt(y, 2)}")
    # Возврат к началу рафта на высоту 2-го слоя
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(raft_x0, 2)} Y{_fmt(raft_y0, 2)} Z{_fmt(lh * 2, 2)}")

    lines.append(";" + _c["layer"] + " 2")
    # Вертикаль (зигзаг, шаг 2 мм)
    x = raft_x0
    while x < raft_x1:
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(x, 2)} Y{_fmt(raft_y1, 2)} E{_fmt(ev, 5)}")
        x = x + 1
        lines.append(f"G0 F{int(ts) * 60} X{_fmt(x, 2)} Y{_fmt(raft_y1, 2)}")
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(x, 2)} Y{_fmt(raft_y0, 2)} E{_fmt(ev, 5)}")
        x = x + 1
        lines.append(f"G0 F{int(ts) * 60} X{_fmt(x, 2)} Y{_fmt(raft_y0, 2)}")
    # Переход к стартовой позиции калибровки (слой 3)
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(tower_x, 2)} Y{_fmt(tower_y, 2)} Z{_fmt(lh * 3, 2)}")

    # Относительная экструзия (координаты — абсолютные, G90)
    lines.append("M83")

    # --- Калибровка ---
    ev = _e_value(params, 10)
    corenermarker = _e_value(params, 1)
    loopbigcount = 0
    layer = 3
    inner_layers = lt - 1
    z = lh * 3

    for _ in range(nt):
        # Вентилятор и температура на каждый тест
        lines.append(f"M106 S{_fmt((fs + fsi * loopbigcount) * 255 / 100, 0)}")
        lines.append(f"M104 S{_fmt(tsh + tih * loopbigcount, 0)}")
        lines.append(f";{_c['layer']} {layer}")

        x, y = tower_x, tower_y

        # Надпись «перед» — только на первом слое, в выступе подложки
        if loopbigcount == 0:
            _print_text(lines, ps, ts, corenermarker, FRONT_LABEL, text_x, text_y)
            lines.append(f"G0 F{int(ts) * 60} X{_fmt(tower_x, 2)} Y{_fmt(tower_y, 2)}")
            x, y = tower_x, tower_y

        # Маркер угла: нижний левый
        x, y = _corner_markers(lines, ps, corenermarker, 2, -1, -1, 1, 1, x, y)
        # Bottom (перед): значения 0..3 (движение X+, втягивание Y-)
        x, y = _side(lines, params, 0, "X", 1, "Y", -1, loopbigcount, ev, ps, ts, x, y)
        # Маркер угла: нижний правый
        x, y = _corner_markers(lines, ps, corenermarker, 1, 1, -1, -1, 1, x, y)
        # Right: значения 4..7 (движение Y+, втягивание X+)
        x, y = _side(lines, params, 4, "Y", 1, "X", 1, loopbigcount, ev, ps, ts, x, y)
        # Маркер угла: верхний правый
        x, y = _corner_markers(lines, ps, corenermarker, 1, 1, 1, -1, -1, x, y)
        # Top (зад): значения 8..11 (движение X-, втягивание Y+)
        x, y = _side(lines, params, 8, "X", -1, "Y", 1, loopbigcount, ev, ps, ts, x, y)
        # Маркер угла: верхний левый
        x, y = _corner_markers(lines, ps, corenermarker, 1, -1, 1, 1, -1, x, y)
        # Left: значения 12..15 (движение Y-, втягивание X-)
        x, y = _side(lines, params, 12, "Y", -1, "X", -1, loopbigcount, ev, ps, ts, x, y)

        # Подъём на высоту слоя
        z = z + lh
        lines.append(f"G1 Z{_fmt(z, 2)}")
        layer = layer + 1

        # Внутренние слои теста (без маркеров углов)
        for _ in range(inner_layers):
            lines.append(f";{_c['layer']} {layer}")
            x, y = tower_x, tower_y
            x, y = _side(lines, params, 0, "X", 1, "Y", -1, loopbigcount, ev, ps, ts, x, y)
            x, y = _side(lines, params, 4, "Y", 1, "X", 1, loopbigcount, ev, ps, ts, x, y)
            x, y = _side(lines, params, 8, "X", -1, "Y", 1, loopbigcount, ev, ps, ts, x, y)
            x, y = _side(lines, params, 12, "Y", -1, "X", -1, loopbigcount, ev, ps, ts, x, y)
            z = z + lh
            lines.append(f"G1 Z{_fmt(z, 2)}")
            layer = layer + 1

        loopbigcount = loopbigcount + 1

    # --- End Game (из профиля принтера или дефолт) ---
    if end_gcode:
        lines.append(end_gcode.strip())

    return "\n".join(lines) + "\n"