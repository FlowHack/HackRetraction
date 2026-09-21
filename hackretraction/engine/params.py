"""ParamsMixin: подтягивание параметров и gcode из профиля принтера.

Также парсинг ранее сгенерированного плагином gcode (секция «All inputs»)
для подгрузки параметров обратно в UI.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..constants import (
    DEFAULT_END_GCODE,
    DEFAULT_START_GCODE,
    END_GCODE_KEY,
    EXTRUDER_ID_KEYS,
    EXTRUDER_PRESETS,
    FAN_SPEED_KEYS,
    PRESET_KEYS,
    START_GCODE_KEY,
)
from ..errors import ProfileError
from ..i18n import I18N_COMMENTS
from ..logging import _LOGGER
from ..orca_compat import orca
from .core import CoreMixin


def _fmt_val(value: float) -> str:
    """Форматирование числа для подстановки в gcode (целые без .0)."""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


# Точечная подстановка плейсхолдеров OrcaSlicer из параметров.
_PLACEHOLDER_FUNCS: Dict[str, Any] = {
    "[bed_temperature_initial_layer_single]": lambda p: p["tempBed"],
    "[nozzle_temperature_initial_layer]": lambda p: p["tempStarthotend"],
    "{print_bed_max[0]*0.5-50}": lambda p: p["dimensionX"] * 0.5 - 50,
    "{print_bed_max[0]*0.5+50}": lambda p: p["dimensionX"] * 0.5 + 50,
    "{print_bed_max[0]*0.5+47}": lambda p: p["dimensionX"] * 0.5 + 47,
    "{print_bed_max[1]}": lambda p: p["dimensionY"],
}


def apply_placeholders(gcode: str, params: Dict[str, float]) -> str:
    """Подставляет плейсхолдеры OrcaSlicer из параметров в gcode принтера."""
    for placeholder, func in _PLACEHOLDER_FUNCS.items():
        if placeholder in gcode:
            gcode = gcode.replace(placeholder, _fmt_val(float(func(params))))
    return gcode


# Порядок значений в секции «All inputs» (совпадает с генератором).
_ALL_INPUTS_ORDER: List[str] = [
    "dimensionX",
    "dimensionY",
    "startRetractiondistance",
    "incrementRetractiondistance",
    "startRetractionspeed",
    "incrementRetractionspeed",
    "printSpeed",
    "tempStarthotend",
    "tempIncrementhotend",
    "tempBed",
    "speedFan",
    "speedFanIncrement",
    "nozzleDiameter",
    "layerHeight",
    "filamentDiameter",
    "extrusionMultiplier",
    "layersTest",
    "NumTests",
]

_ALL_INPUTS_MARKERS: List[str] = [
    I18N_COMMENTS[lang]["all_inputs"] for lang in ("en", "ru", "sr")
]


def parse_gcode(text: str) -> Dict[str, Any]:
    """Парсит секцию «All inputs» сгенерированного gcode в параметры.

    Возвращает словарь параметров (как DEFAULT_PARAMS). Родной язык файла
    не важен — заголовок ищется по любому из трёх языков.
    """
    lines = text.splitlines()
    start: Optional[int] = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(";") and stripped[1:].strip() in _ALL_INPUTS_MARKERS:
            start = idx + 1
            break
    if start is None:
        raise ProfileError("Не найдена секция «All inputs» в gcode")

    params: Dict[str, Any] = {}
    pos = 0
    for line in lines[start:]:
        if pos >= len(_ALL_INPUTS_ORDER):
            break
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*$", line)
        if match:
            params[_ALL_INPUTS_ORDER[pos]] = float(match.group(1))
            pos += 1

    if pos < len(_ALL_INPUTS_ORDER):
        raise ProfileError(
            "Секция «All inputs» неполная: ожидалось "
            f"{len(_ALL_INPUTS_ORDER)} значений, найдено {pos}"
        )
    return params


def _parse_printable_area(area: Any) -> Optional[tuple[float, float]]:
    """Парсит printable_area в (ширина, глубина) или None.

    Формат OrcaSlicer — 4 точки прямоугольника: "0x0,325x0,325x325,0x325"
    (x0,y0, x1,y0, x1,y1, x0,y1). Значение может прийти строкой или списком.
    """
    if isinstance(area, str):
        parts = [p.strip() for p in area.split(",")]
    elif isinstance(area, (list, tuple)):
        parts = [str(p).strip() for p in area]
    else:
        return None
    if len(parts) < 4:
        return None
    try:
        x1 = float(parts[2].split("x")[0])
        y1 = float(parts[2].split("x")[1])
    except (ValueError, IndexError):
        return None
    if x1 <= 0 or y1 <= 0:
        return None
    return x1, y1


class ParamsMixin(CoreMixin):
    """Подтягивание параметров, стартового/конечного gcode и типа экструдера."""

    def pull_from_profile(self) -> Dict[str, Any]:
        """Подтягивает параметры и gcode из профиля принтера (если Orca есть).

        Возвращает dict: params (подтянутые значения), start_gcode, end_gcode,
        extruder ('bowden'/'direct'/'unknown'), ok (bool). Пустой start/end —
        означает «использовать дефолт».
        """
        result: Dict[str, Any] = {
            "params": {},
            "start_gcode": "",
            "end_gcode": "",
            "extruder": "unknown",
            "ok": False,
        }
        if orca is None:
            return result

        try:
            bundle = orca.host.preset_bundle()  # type: ignore[attr-defined]

            def _getv(key: str) -> Any:
                # merged-конфиг всего пресета (printer+filament+print), а не
                # только секции printers — иначе filament/print ключи не видны.
                value = bundle.full_config_value(key)
                return getattr(value, "value", value)

            # Параметры из PRESET_KEYS
            for ui_key, preset_key in PRESET_KEYS.items():
                try:
                    value = _getv(preset_key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        result["params"][ui_key] = float(value)
                except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                    _LOGGER.debug("Нет параметра %s в профиле: %s", preset_key, exc)

            # Обдув: полусумма fan_min_speed и fan_max_speed (типично min=0 —
            # получаем половину максимума; при ненулевом min учитывается и он).
            try:
                fan_min = _getv(FAN_SPEED_KEYS[0])
                fan_max = _getv(FAN_SPEED_KEYS[1])
                if (
                    isinstance(fan_min, (int, float)) and not isinstance(fan_min, bool)
                    and isinstance(fan_max, (int, float)) and not isinstance(fan_max, bool)
                ):
                    result["params"]["speedFan"] = round(
                        (float(fan_min) + float(fan_max)) / 2, 1
                    )
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                _LOGGER.debug("Нет обдува (fan_min/max) в профиле: %s", exc)

            # Размеры стола: printable_width/printable_depth есть не у всех
            # принтеров — fallback на printable_area (4 точки прямоугольника).
            if "dimensionX" not in result["params"] or "dimensionY" not in result["params"]:
                try:
                    size = _parse_printable_area(_getv("printable_area"))
                    if size is not None:
                        result["params"]["dimensionX"] = size[0]
                        result["params"]["dimensionY"] = size[1]
                except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                    _LOGGER.debug("Нет printable_area в профиле: %s", exc)

            # Стартовый/конечный gcode (пусто — дефолт).
            # Orca отдаёт gcode с литеральными \n — нормализуем в переносы.
            try:
                start = _getv(START_GCODE_KEY)
                result["start_gcode"] = (
                    str(start).replace("\\n", "\n") if start else ""
                )
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                _LOGGER.debug("Нет стартового gcode: %s", exc)
            try:
                end = _getv(END_GCODE_KEY)
                result["end_gcode"] = str(end).replace("\\n", "\n") if end else ""
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                _LOGGER.debug("Нет конечного gcode: %s", exc)

            # Тип экструдера (bowden/direct)
            for key in EXTRUDER_ID_KEYS:
                try:
                    raw = str(_getv(key) or "").lower()
                    if "bowden" in raw:
                        result["extruder"] = "bowden"
                        break
                    if "direct" in raw:
                        result["extruder"] = "direct"
                        break
                except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                    _LOGGER.debug("Нет типа экструдера %s: %s", key, exc)

            result["ok"] = True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Не удалось подтянуть параметры из профиля: %s", exc)
            result["ok"] = False
        return result

    def apply_extruder_presets(self, params: Dict[str, Any], extruder: str) -> None:
        """Накладывает стартовые значения для типа экструдера на params."""
        preset = EXTRUDER_PRESETS.get(extruder)
        if preset:
            params.update(preset)

    def _apply_pull_result(self, result: Dict[str, Any]) -> None:
        """Применяет результат pull_from_profile к состоянию движка.

        Обновляет только подтянутые параметры, накладывает пресеты
        экструдера и сохраняет подтянутые gcode. Остальные поля не трогает.
        """
        params = self.get_params()
        params.update(result["params"])
        self.apply_extruder_presets(params, result["extruder"])
        self.set_params(params)
        self.set_start_end_gcode(result["start_gcode"], result["end_gcode"])

    def _auto_pull(self) -> None:
        """Подтягивает параметры из профиля при старте плагина.

        Вызывается один раз при создании движка: все подтягиваемые значения
        (параметры, gcode, пресеты экструдера) применяются к состоянию.
        Вне Orca (или при ошибке) ничего не делает.
        """
        result = self.pull_from_profile()
        if result["ok"]:
            self._apply_pull_result(result)

    def resolved_start_end(self, params: Dict[str, Any]) -> tuple[str, str]:
        """Возвращает (start_gcode, end_gcode) с подставленными плейсхолдерами.

        Приоритет: отредактированный пользователем gcode из params →
        подтянутый из профиля → дефолт из constants.py. Плейсхолдеры
        OrcaSlicer подставляются из параметров.
        """
        start = params.get("startGcode") or self._start_gcode or DEFAULT_START_GCODE
        end = params.get("endGcode") or self._end_gcode or DEFAULT_END_GCODE
        start = apply_placeholders(start, params)
        end = apply_placeholders(end, params)
        return start, end

    def _resolve_params_for_gen(self, incoming: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        params = self.get_params()
        if incoming:
            self.set_params(incoming)
            params = self.get_params()
        return params
