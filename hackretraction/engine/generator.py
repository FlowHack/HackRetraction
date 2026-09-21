"""Генератор gcode калибровочного куба ретракции.

Логика перенесена из fork/RetCalMain.py (версия 1.3.1) с существенными
изменениями:
- стартовый и конечный gcode берутся из профиля принтера (или дефолтов),
  а не зашиты жёстко;
- таблица "Variables by Height" идёт от 0 до nt-1 (консистентно с кодом
  калибровки, в оригинале — в обратном порядке);
- послойная схема (Z только растёт, без прыжков вниз):
  слои 1-2 — общая подложка (рафт-зигзаг на всю область);
  слой 3 — надпись FRONT_LABEL («HACKRETRACTION») жирными периметрами
  палочного шрифта + локальная подложка под башней (квадрат 60x60,
  центрирован по центру башни);
  слой 4 — то же (текст завершён);
  слои 5..N (N = 4 + nt*lt) — калибровочная башня;
- перемещения — в АБСОЛЮТНЫХ координатах (G90): слайсеры корректно
  отображают превью только без G91. Подложка, надпись и башня
  центрируются относительно стола и никогда не разъезжаются. Штрихи букв
  надписи тоже в G90: скелет буквы переводится в абсолютные координаты
  стола, вокруг каждого штриха строится U-образная петля из двух
  эквидистант;
- подложка — сплошной зигзаг 60x68, выступ снизу под надпись; надпись
  масштабирована 0.7 по ширине башни:
  слои 1-2 заливаются от края до края без вырезов, буквы печатаются
  поверх подложки выпуклыми линиями (не вырезаются из неё);
- переезды между фазами — единый паттерн: ретракт → G0 XY → G0 Z →
  сброс счётчика экструдера (G92 E0) на старте следующей фазы.
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
    lines: List[str], ps: float, marker: float, size: int,
    sx1: int, sy1: int, x: float, y: float
) -> Tuple[float, float]:
    # Рисуем квадрат и возвращаемся строго в исходные x, y
    lines.append(f"G1 F{int(ps * 60)} X{_fmt(x + sx1 * size, 2)} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} Y{_fmt(y + sy1 * size, 2)} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} X{_fmt(x, 2)} E{_fmt(marker, 5)}")
    lines.append(f"G1 F{int(ps * 60)} Y{_fmt(y, 2)} E{_fmt(marker, 5)}")
    return x, y


def _offset_polyline(pts: List[Tuple[float, float]], offset: float) -> List[Tuple[float, float]]:
    """Вычисляет эквидистанту (смещение) полилинии по нормалям."""
    if len(pts) < 2:
        return pts
    out = []
    for i, p in enumerate(pts):
        p_prev = pts[i - 1] if i > 0 else None
        p_next = pts[i + 1] if i < len(pts) - 1 else None

        n1 = n2 = None
        if p_prev:
            dx, dy = p[0] - p_prev[0], p[1] - p_prev[1]
            L = (dx**2 + dy**2) ** 0.5
            if L > 0:
                n1 = (-dy / L, dx / L)
        if p_next:
            dx, dy = p_next[0] - p[0], p_next[1] - p[1]
            L = (dx**2 + dy**2) ** 0.5
            if L > 0:
                n2 = (-dy / L, dx / L)

        if not n1:
            n1 = n2
        if not n2:
            n2 = n1

        # Вырожденные сегменты (L == 0) — нормали не вычислены, точку пропускаем
        if n1 is None or n2 is None:
            continue

        nx, ny = n1[0] + n2[0], n1[1] + n2[1]
        L = (nx**2 + ny**2) ** 0.5
        if L == 0:
            nx, ny = -n1[1], n1[0]
        else:
            nx, ny = nx / L, ny / L
            dot = nx * n1[0] + ny * n1[1]
            if dot > 0.2:  # Лимит остроты углов во избежание бесконечных шипов
                nx, ny = nx / dot, ny / dot

        out.append((p[0] + nx * offset, p[1] + ny * offset))
    return out


# Буквы разбиты на отдельные штрихи (списки координат), чтобы сопло
# могло перемещаться с выключенной экструзией (G0) внутри сложных букв.
# В данных шрифта Y+ — вниз; при печати ось Y инвертируется (см. _stroke_text),
# поэтому на столе буквы стоят на базовой линии и читаются слева направо.
_STROKE_FONT: Dict[str, List[List[Tuple[float, float]]]] = {
    "H": [[(0, 0), (0, 7)], [(0, 3.5), (5, 3.5)], [(5, 0), (5, 7)]],
    "A": [[(0, 7), (2.5, 0), (5, 7)], [(1.25, 4), (3.75, 4)]],
    "C": [[(5, 1.5), (3.5, 0), (1.5, 0), (0, 1.5), (0, 5.5), (1.5, 7), (3.5, 7), (5, 5.5)]],
    "K": [[(0, 0), (0, 7)], [(5, 0), (0, 3.5), (5, 7)]],
    "R": [[(0, 0), (0, 7)], [(0, 0), (4, 0), (5, 1), (5, 3), (4, 4), (0, 4)], [(2.5, 4), (5, 7)]],
    "E": [[(5, 0), (0, 0), (0, 7), (5, 7)], [(0, 3.5), (4, 3.5)]],
    "T": [[(0, 0), (5, 0)], [(2.5, 0), (2.5, 7)]],
    "I": [[(2.5, 0), (2.5, 7)]],
    "O": [[(1.5, 0), (3.5, 0), (5, 1.5), (5, 5.5), (3.5, 7), (1.5, 7),
           (0, 5.5), (0, 1.5), (1.5, 0)]],
    "N": [[(0, 7), (0, 0), (5, 7), (5, 0)]],
}

FRONT_LABEL = "HACKRETRACTION"


def _stroke_text(
    lines: List[str],
    params: Dict[str, float],
    text: str,
    start_x: float,
    start_y: float,
    ps: float,
    ts: float,
    start_retracted: bool = False,
    scale: float = 0.7,
) -> bool:
    """Печать текста жирными периметрами (2 стенки по нормалям, G90).

    Скелет буквы переводится в абсолютные координаты стола (ось Y
    инвертируется: в данных шрифта Y+ — вниз, на столе Y+ — вверх).
    Вокруг каждого штриха строится U-образная петля из двух эквидистант
    (_offset_polyline на ±пол-сопла), которая печатается как цельный
    периметр. Между штрихами и буквами — ретракт.

    scale — масштаб скелета букв: координаты штрихов и шаг между буквами
    умножаются на scale, offset (nd/2) не масштабируется — толщина линий
    остаётся 2×nd.

    G90/M83/G92 E0 эмитятся один раз в generate_gcode перед первым
    вызовом — здесь они не дублируются. Сопло остаётся втянутым после
    последнего штриха (двойной ретракт не выполняется).

    Возвращает конечное состояние is_retracted (True — сопло втянуто).
    """
    srd = float(params["startRetractiondistance"])
    srs = float(params["startRetractionspeed"])
    nd = float(params["nozzleDiameter"])
    offset = nd / 2.0  # Смещение на пол-сопла (дает суммарно 2 периметра толщины)

    current_x = start_x
    is_retracted = start_retracted

    for ch in text.upper():
        strokes = _STROKE_FONT.get(ch)
        if not strokes:
            current_x += 6 * scale
            continue

        for stroke in strokes:
            # 1. Переводим штрих в абсолютные координаты (инвертируя Y)
            abs_stroke = [(current_x + px * scale, start_y - py * scale) for px, py in stroke]

            # 2. Высчитываем наружный и внутренний контур
            path1 = _offset_polyline(abs_stroke, offset)
            path2 = _offset_polyline(abs_stroke, -offset)
            path2.reverse()  # Разворачиваем для замкнутой петли

            # 3. Соединяем в U-образный контур-периметр
            full_path = path1 + path2 + [path1[0]]

            # 4. Холостой ход к старту периметра
            px, py = full_path[0]
            lines.append(f"G0 F{int(ts) * 60} X{_fmt(px, 2)} Y{_fmt(py, 2)}")

            if is_retracted:
                lines.append(f"G1 F{int(srs * 60)} E{_fmt(srd, 2)}")
                is_retracted = False

            # 5. Печатаем периметр буквы (50% от основной скорости)
            for tx, ty in full_path[1:]:
                dx, dy = tx - px, ty - py
                dist = (dx**2 + dy**2) ** 0.5
                lines.append(
                    f"G1 F{int(ps * 60 / 2)} X{_fmt(tx, 2)} Y{_fmt(ty, 2)} "
                    f"E{_fmt(_e_value(params, dist), 5)}"
                )
                px, py = tx, ty

            # Делаем ретракт перед переходом к следующему штриху/букве
            lines.append(f"G1 F{int(srs * 60)} E-{_fmt(srd, 2)}")
            is_retracted = True

        current_x += 6 * scale

    return is_retracted


def _local_raft(
    lines: List[str],
    params: Dict[str, float],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    ps: float,
    vertical: bool = False,
) -> float:
    """Локальная подложка под башней: зигзаг в ограниченной области.

    Режим M83 (относительная экструзия), перед началом — G92 E0.
    Каждая команда E — приращение текущего отрезка:
    _e_value(params, длина_линии) * 1.25, шаг 1 мм,
    скорость ps*60/2 (как у общей подложки). vertical=True — линии
    идут по Y (как слой 2 общей подложки), иначе — по X (слой 1).
    Возвращает 0.0 (фиктивное значение, сигнатура сохранена).
    """
    feed = f"G1 F{int(ps * 60 / 2)}"
    if not vertical:
        # Горизонтальные линии (по X), переходы по краю — 1 мм по Y
        ev_x_inc = _e_value(params, x1 - x0) * 1.25
        ev_1mm = _e_value(params, 1.0) * 1.25
        y = y0
        while y <= y1:
            lines.append(f"{feed} X{_fmt(x1, 2)} Y{_fmt(y, 2)} E{_fmt(ev_x_inc, 5)}")
            y += 1
            if y > y1:
                break
            lines.append(f"{feed} X{_fmt(x1, 2)} Y{_fmt(y, 2)} E{_fmt(ev_1mm, 5)}")

            lines.append(f"{feed} X{_fmt(x0, 2)} Y{_fmt(y, 2)} E{_fmt(ev_x_inc, 5)}")
            y += 1
            if y > y1:
                break
            lines.append(f"{feed} X{_fmt(x0, 2)} Y{_fmt(y, 2)} E{_fmt(ev_1mm, 5)}")
    else:
        # Вертикальные линии (по Y), переходы по краю — 1 мм по X
        ev_y_inc = _e_value(params, y1 - y0) * 1.25
        ev_1mm = _e_value(params, 1.0) * 1.25
        x = x0
        while x <= x1:
            lines.append(f"{feed} X{_fmt(x, 2)} Y{_fmt(y1, 2)} E{_fmt(ev_y_inc, 5)}")
            x += 1
            if x > x1:
                break
            lines.append(f"{feed} X{_fmt(x, 2)} Y{_fmt(y1, 2)} E{_fmt(ev_1mm, 5)}")

            lines.append(f"{feed} X{_fmt(x, 2)} Y{_fmt(y0, 2)} E{_fmt(ev_y_inc, 5)}")
            x += 1
            if x > x1:
                break
            lines.append(f"{feed} X{_fmt(x, 2)} Y{_fmt(y0, 2)} E{_fmt(ev_1mm, 5)}")
    return 0.0


def _tower_layer(
    lines: List[str],
    params: Dict[str, float],
    test_idx: int,
    layer_in_test: int,
    ev: float,
    ps: float,
    ts: float,
    x: float,
    y: float,
    z: float,
) -> Tuple[float, float, float]:
    """Один слой калибровочной башни.

    Маркеры углов и команды M106/M104 (вентилятор/температура) эмитятся
    только на первом слое теста (layer_in_test == 0); остальные слои —
    только 4 стороны. x, y — якорь башни (tower_x, tower_y).
    Возвращает (x, y, z) после слоя.
    """
    lh = float(params["layerHeight"])
    fs = float(params["speedFan"])
    fsi = float(params["speedFanIncrement"])
    tsh = float(params["tempStarthotend"])
    tih = float(params["tempIncrementhotend"])
    corenermarker = _e_value(params, 1)

    if layer_in_test == 0:
        # Вентилятор и температура на каждый тест
        lines.append(f"M106 S{_fmt((fs + fsi * test_idx) * 255 / 100, 0)}")
        lines.append(f"M104 S{_fmt(tsh + tih * test_idx, 0)}")

    if layer_in_test == 0:
        # Маркер угла: нижний левый
        x, y = _corner_markers(lines, ps, corenermarker, 2, -1, -1, x, y)
    # Bottom (перед): значения 0..3 (движение X+, втягивание Y-)
    x, y = _side(lines, params, 0, "X", 1, "Y", -1, test_idx, ev, ps, ts, x, y)
    if layer_in_test == 0:
        # Маркер угла: нижний правый
        x, y = _corner_markers(lines, ps, corenermarker, 1, 1, -1, x, y)
    # Right: значения 4..7 (движение Y+, втягивание X+)
    x, y = _side(lines, params, 4, "Y", 1, "X", 1, test_idx, ev, ps, ts, x, y)
    if layer_in_test == 0:
        # Маркер угла: верхний правый
        x, y = _corner_markers(lines, ps, corenermarker, 1, 1, 1, x, y)
    # Top (зад): значения 8..11 (движение X-, втягивание Y+)
    x, y = _side(lines, params, 8, "X", -1, "Y", 1, test_idx, ev, ps, ts, x, y)
    if layer_in_test == 0:
        # Маркер угла: верхний левый
        x, y = _corner_markers(lines, ps, corenermarker, 1, -1, 1, x, y)
    # Left: значения 12..15 (движение Y-, втягивание X-)
    x, y = _side(lines, params, 12, "Y", -1, "X", -1, test_idx, ev, ps, ts, x, y)

    # Подъём на высоту следующего слоя
    z = z + lh
    lines.append(f"G1 Z{_fmt(z, 2)}")
    return x, y, z


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
    lines.append(
        f";{_fmt(srd + ird * 12, 2)}-"
        "                               "
        f"-{_fmt(srd + ird * 7, 2)}"
    )
    lines.append(";")
    lines.append(";")
    lines.append(
        f";{_fmt(srd + ird * 13, 2)}-"
        "                               "
        f"-{_fmt(srd + ird * 6, 2)}"
    )
    lines.append(";")
    lines.append(";")
    lines.append(
        f";{_fmt(srd + ird * 14, 2)}-"
        "                               "
        f"-{_fmt(srd + ird * 5, 2)}"
    )
    lines.append(";")
    lines.append(";")
    lines.append(
        f";{_fmt(srd + ird * 15, 2)}-"
        "                               "
        f"-{_fmt(srd + ird * 4, 2)}"
    )
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

    # --- Start Gcode (из профиля принтера или дефолт) ---
    lines.append(";" + _c["start_gcode"])
    if start_gcode:
        lines.append(start_gcode.strip())
    lines.append(";")
    lines.append(";")

    # --- Start Movement (абсолютные координаты, G90) ---
    cx = dx / 2
    cy = dy / 2

    # Текст (масштаб 0.7: ширина 14 букв = 58.8 мм, высота = 4.9 мм)
    text_scale = 0.7
    text_x = cx - 29.4  # Идеальное центрирование (отступ по 0.6 мм по бокам)
    text_y = cy - 31.0  # Базовая линия текста (верх), зазор 1 мм до локальной подложки

    # Общая подложка 1-2 слоя (компактная: 60x68 мм)
    # Слева, справа и сверху ТОЧНО совпадает с локальной подложкой (±30 мм от центра)
    raft_x0 = cx - 30.0
    raft_x1 = cx + 30.0
    raft_y1 = cy + 30.0
    # Низ выступает ровно под текст (текст заканчивается на cy-35.9)
    raft_y0 = cy - 38.0

    tower_x = cx - 25
    tower_y = cy - 25

    # Локальная подложка под башней (слои 3-4): квадрат 60x60
    lraft_x0 = cx - 30.0
    lraft_y0 = cy - 30.0
    lraft_x1 = cx + 30.0
    lraft_y1 = cy + 30.0
    lines.append(";" + _c["start_movement"])
    lines.append(";")
    lines.append("M82 ; Включаем абсолютную экструзию для подложки")
    lines.append("G92 E0 ; Сбрасываем счетчик экструдера")
    lines.append("G90")
    lines.append("G1 Z2")
    lines.append(f"G1 F{int(ts) * 60} X{_fmt(raft_x0, 2)} Y{_fmt(raft_y0, 2)} Z{_fmt(lh, 2)}")
    lines.append(";")

    # --- Рафт (Слой 1): горизонталь, шаг 1 мм, E под длину линии 60 мм ---
    ev = 0.0
    ev_x_inc = _e_value(params, raft_x1 - raft_x0) * 1.25
    # Экструзия для рабочего перехода по краю (1 мм вдоль края)
    ev_y_inc_1mm = _e_value(params, 1.0) * 1.25  # слой 1: переходы идут по Y
    ev_x_inc_1mm = _e_value(params, 1.0) * 1.25  # слой 2: переходы идут по X
    lines.append(";" + _c["layer"] + " 1")
    y = raft_y0
    while y <= raft_y1:
        ev += ev_x_inc
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(raft_x1, 2)} Y{_fmt(y, 2)} E{_fmt(ev, 5)}")
        y += 1
        if y > raft_y1:
            break
        ev += ev_y_inc_1mm
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(raft_x1, 2)} Y{_fmt(y, 2)} E{_fmt(ev, 5)}")

        ev += ev_x_inc
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(raft_x0, 2)} Y{_fmt(y, 2)} E{_fmt(ev, 5)}")
        y += 1
        if y > raft_y1:
            break
        ev += ev_y_inc_1mm
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(raft_x0, 2)} Y{_fmt(y, 2)} E{_fmt(ev, 5)}")

    # Физический ретракт перед переездом на 2-й слой
    ev_retract = ev - srd
    lines.append(f"G1 F1800 E{_fmt(ev_retract, 5)}")
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(raft_x0, 2)} Y{_fmt(raft_y0, 2)} Z{_fmt(lh * 2, 2)}")
    lines.append(f"G1 F1800 E{_fmt(ev, 5)}")

    # --- Рафт (Слой 2): вертикаль, шаг 1 мм, E под длину линии 68 мм ---
    ev_y_inc = _e_value(params, raft_y1 - raft_y0) * 1.25
    lines.append(";" + _c["layer"] + " 2")
    x = raft_x0
    while x <= raft_x1:
        ev += ev_y_inc
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(x, 2)} Y{_fmt(raft_y1, 2)} E{_fmt(ev, 5)}")
        x += 1
        if x > raft_x1:
            break
        ev += ev_x_inc_1mm
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(x, 2)} Y{_fmt(raft_y1, 2)} E{_fmt(ev, 5)}")

        ev += ev_y_inc
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(x, 2)} Y{_fmt(raft_y0, 2)} E{_fmt(ev, 5)}")
        x += 1
        if x > raft_x1:
            break
        ev += ev_x_inc_1mm
        lines.append(f"G1 F{int(ps * 60 / 2)} X{_fmt(x, 2)} Y{_fmt(raft_y0, 2)} E{_fmt(ev, 5)}")

    # Переход рафт → буквы (слой 3): физический ретракт → G0 XY → G0 Z
    ev_retract = ev - srd
    lines.append(f"G1 F1800 E{_fmt(ev_retract, 5)}")
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(text_x, 2)} Y{_fmt(text_y, 2)}")
    lines.append(f"G0 F{int(ts) * 60} Z{_fmt(lh * 3, 2)}")
    # Относительная экструзия (координаты — абсолютные, G90)
    lines.append("M83")
    lines.append("G92 E0 ; Сброс счетчика экструдера")

    # --- Слой 3: буквы → переезд → локальная подложка ---
    lines.append(f";{_c['layer']} 3 (Text)")
    # Сопло входит втянутым (start_retracted=True) и остаётся втянутым
    # после последнего штриха — переезд к подложке безопасен
    _stroke_text(
        lines, params, FRONT_LABEL, text_x, text_y, ps, ts,
        start_retracted=True, scale=text_scale,
    )

    # Переход буквы → локальная подложка (слой 3): сопло втянуто, Z не меняется
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(lraft_x0, 2)} Y{_fmt(lraft_y0, 2)}")
    lines.append("G92 E0 ; Сброс счетчика экструдера")
    # Сопло физически втянуто на srd после текста — возвращаем филамент,
    # иначе первая линия подложки печатается «вхолостую»
    lines.append(f"G1 F{int(srs * 60)} E{_fmt(srd, 2)}")
    lines.append(f";{_c['layer']} 3{_c['local_raft']}")
    _local_raft(lines, params, lraft_x0, lraft_y0, lraft_x1, lraft_y1, ps)

    # --- Слой 4: буквы → переезд → локальная подложка ---
    # Переход локальная подложка → буквы (слой 4): ретракт → G0 XY → G0 Z
    lines.append(f"G1 F{int(srs * 60)} E-{_fmt(srd, 2)}")
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(text_x, 2)} Y{_fmt(text_y, 2)}")
    lines.append(f"G0 F{int(ts) * 60} Z{_fmt(lh * 4, 2)}")
    lines.append(f";{_c['layer']} 4 (Text)")
    _stroke_text(
        lines, params, FRONT_LABEL, text_x, text_y, ps, ts,
        start_retracted=True, scale=text_scale,
    )

    # Переход буквы → локальная подложка (слой 4): сопло втянуто, Z не меняется
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(lraft_x0, 2)} Y{_fmt(lraft_y0, 2)}")
    lines.append("G92 E0 ; Сброс счетчика экструдера")
    # Сопло физически втянуто на srd после текста — возвращаем филамент,
    # иначе первая линия подложки печатается «вхолостую»
    lines.append(f"G1 F{int(srs * 60)} E{_fmt(srd, 2)}")
    lines.append(f";{_c['layer']} 4{_c['local_raft']}")
    _local_raft(lines, params, lraft_x0, lraft_y0, lraft_x1, lraft_y1, ps, vertical=True)

    # --- Переход локальная подложка → башня (слой 5) ---
    lines.append(f"G1 F{int(srs * 60)} E-{_fmt(srd, 2)}")
    lines.append(f"G0 F{int(ts) * 60} X{_fmt(tower_x, 2)} Y{_fmt(tower_y, 2)}")
    lines.append(f"G0 F{int(ts) * 60} Z{_fmt(lh * 5, 2)}")
    lines.append("G92 E0 ; Сброс счетчика экструдера")
    # Сопло физически втянуто на srd после ретракта — возвращаем филамент,
    # иначе первый маркер угла и первая линия печатаются «вхолостую»
    lines.append(f"G1 F{int(srs * 60)} E{_fmt(srd, 2)}")

    # --- Калибровочная башня (слои 5..N, N = 4 + nt*lt) ---
    ev = _e_value(params, 10)
    z = lh * 5
    layer = 5
    for test_idx in range(nt):
        for layer_in_test in range(lt):
            lines.append(f";{_c['layer']} {layer}")
            _, _, z = _tower_layer(
                lines, params, test_idx, layer_in_test, ev, ps, ts,
                tower_x, tower_y, z,
            )
            layer += 1

    # --- End Game (из профиля принтера или дефолт) ---
    if end_gcode:
        lines.append(end_gcode.strip())

    return "\n".join(lines) + "\n"
