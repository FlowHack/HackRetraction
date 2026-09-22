"""ParamsMixin: подтягивание параметров и gcode из профиля принтера.

Также парсинг ранее сгенерированного плагином gcode (секция «All inputs»)
для подгрузки параметров обратно в UI.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..constants import (
    DEFAULT_END_GCODE,
    END_GCODE_KEY,
    EXTRUDER_ID_KEYS,
    EXTRUDER_PRESETS,
    FAN_SPEED_KEYS,
    FIRMWARE_FLAVOR_MAP,
    KEY_SECTIONS,
    PRESET_KEYS,
    START_GCODE_KEY,
    default_start_gcode_for,
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


def _to_float(value: Any) -> Optional[float]:
    """Нормализует значение пресета в float: строка/массив/число.

    "210;210" → первый элемент, "85%" → 85, "nil"/пусто → None.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (list, tuple)):
        return _to_float(value[0]) if value else None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().split(";", maxsplit=1)[0].rstrip("%")
    if not text or text.lower() == "nil":
        return None
    try:
        return float(text)
    except ValueError:
        return None


# Точечная подстановка плейсхолдеров OrcaSlicer из параметров.
# Лямбды возвращают None, если параметр не подтянут (None/отсутствует) —
# такой плейсхолдер остаётся в gcode как есть (см. apply_placeholders).
_PLACEHOLDER_FUNCS: Dict[str, Any] = {
    "[bed_temperature_initial_layer_single]": lambda p: p.get("tempBed"),
    "[nozzle_temperature_initial_layer]": lambda p: p.get("tempStarthotend"),
    "{print_bed_max[0]*0.5-50}": lambda p: (
        p["dimensionX"] * 0.5 - 50 if p.get("dimensionX") is not None else None
    ),
    "{print_bed_max[0]*0.5+50}": lambda p: (
        p["dimensionX"] * 0.5 + 50 if p.get("dimensionX") is not None else None
    ),
    "{print_bed_max[0]*0.5+47}": lambda p: (
        p["dimensionX"] * 0.5 + 47 if p.get("dimensionX") is not None else None
    ),
    "{print_bed_max[1]}": lambda p: p.get("dimensionY"),
}


def apply_placeholders(gcode: str, params: Dict[str, float]) -> str:
    """Подставляет плейсхолдеры OrcaSlicer из параметров в gcode принтера.

    Если параметр для плейсхолдера не подтянут (None) — плейсхолдер
    остаётся в тексте как есть, чтобы пользователь видел незаполненность.
    """
    for placeholder, func in _PLACEHOLDER_FUNCS.items():
        if placeholder in gcode:
            value = func(params)
            if value is None:
                continue
            gcode = gcode.replace(placeholder, _fmt_val(float(value)))
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

    def pull_from_profile(self) -> Dict[str, Any]:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
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
            "firmware": None,
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

            # Параметры из PRESET_KEYS. Значения в профилях Orca хранятся
            # строками/массивами строк — нормализуем через _to_float.
            for ui_key, preset_keys in PRESET_KEYS.items():
                for preset_key in preset_keys:
                    try:
                        num = _to_float(_getv(preset_key))
                    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                        _LOGGER.debug("Нет параметра %s в профиле: %s", preset_key, exc)
                        num = None
                    if num is None:
                        # Резервный проход по цепочке наследования пресета.
                        try:
                            num = _to_float(self._preset_chain_value(bundle, preset_key))
                        except (
                            AttributeError, KeyError, RuntimeError, TypeError, ValueError
                        ) as exc:
                            _LOGGER.debug("Нет %s в цепочке пресета: %s", preset_key, exc)
                            num = None
                    if num is not None:
                        result["params"][ui_key] = num
                        break

            # Обдув: полусумма fan_min_speed и fan_max_speed (типично min=0 —
            # получаем половину максимума; при ненулевом min учитывается и он).
            try:
                fan_min = _to_float(_getv(FAN_SPEED_KEYS[0]))
                fan_max = _to_float(_getv(FAN_SPEED_KEYS[1]))
                if fan_min is not None and fan_max is not None:
                    result["params"]["speedFan"] = round((fan_min + fan_max) / 2, 1)
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

            # Тип прошивки (gcode_flavor) — для дефолтного стартового gcode.
            # Значения Orca: marlin, marlin2, klipper, repetier, reprapfirmware.
            try:
                flavor = str(_getv("gcode_flavor") or "").lower()
                result["firmware"] = FIRMWARE_FLAVOR_MAP.get(flavor)
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                _LOGGER.debug("Нет gcode_flavor в профиле: %s", exc)
                result["firmware"] = None

            if not result["params"]:
                _LOGGER.warning("Подтяжка не нашла ни одного параметра в профиле")

            result["ok"] = True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Не удалось подтянуть параметры из профиля: %s", exc)
            result["ok"] = False
        return result

    def _preset_chain_value(self, bundle: Any, key: str) -> Any:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        """Ищет значение ключа по цепочке наследования пресета (текущий → родитель → ...).

        Возвращает первое непустое значение или None. Секция определяется по KEY_SECTIONS.
        """
        section = KEY_SECTIONS.get(key)
        if not section:
            return None
        try:
            collection = getattr(bundle, section, None)
            if collection is None:
                return None
            preset = getattr(collection, "get_selected_preset", None)
            if callable(preset):
                preset = preset()
            if preset is None:
                return None
            chain: list[Any] = []
            seen: set[str] = set()
            cur = preset
            for _ in range(20):
                if cur is None:
                    break
                name = str(getattr(cur, "name", "") or "")
                if name in seen:
                    break
                seen.add(name)
                chain.append(cur)
                parent_name = ""
                value_fn = getattr(cur, "config_value", None)
                if callable(value_fn):
                    try:
                        raw_inherits = value_fn("inherits")
                        parent_name = str(
                            getattr(raw_inherits, "value", raw_inherits) or ""
                        )
                    except (TypeError, RuntimeError, ValueError):
                        parent_name = ""
                if not parent_name:
                    break
                finder = getattr(collection, "find_preset", None)
                if not callable(finder):
                    break
                try:
                    cur = finder(parent_name)
                except (TypeError, RuntimeError, ValueError):
                    break
            # Merge от корня к текущему: значения дочерних уровней перекрывают
            # родительские (каждое непустое значение перезаписывает предыдущее).
            merged: Any = None
            for item in reversed(chain):
                value_fn = getattr(item, "config_value", None)
                if not callable(value_fn):
                    continue
                try:
                    raw = value_fn(key)
                except (TypeError, RuntimeError, ValueError):
                    continue
                raw = getattr(raw, "value", raw)
                if raw is None:
                    continue
                if isinstance(raw, str) and not raw.strip():
                    continue
                merged = raw
            return merged
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            _LOGGER.debug("Резервный проход по цепочке %s не удался: %s", key, exc)
        return None

    def apply_extruder_presets(self, params: Dict[str, Any], extruder: str) -> None:
        """Накладывает стартовые значения для типа экструдера на params."""
        preset = EXTRUDER_PRESETS.get(extruder)
        if preset:
            params.update(preset)

    def _compute_recommended(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Собирает «рекомендуемый» набор значений из результата подтяжки.

        Рекомендуемое = подтянутые из профиля параметры + пресет экструдера
        (стартовые втягивания/скорости для bowden/direct). Это эталон для
        кнопок сброса числовых полей в UI.
        """
        rec: Dict[str, Any] = dict(result["params"])
        extruder = result["extruder"]
        preset = EXTRUDER_PRESETS.get(extruder)
        if preset:
            rec.update(preset)
        return rec

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
        self._recommended = self._compute_recommended(result)
        # Прошивка из профиля — источник истины для дефолтного gcode.
        # Загружаем конфиг (с дефолтами) перед записью, чтобы не потерять
        # остальные настройки и не сломать ленивую загрузку.
        if result.get("firmware"):
            cfg = dict(self.config)
            cfg["firmware"] = result["firmware"]
            self._config = cfg

    def _auto_pull(self) -> None:
        """Подтягивает параметры из профиля при старте плагина.

        Вызывается один раз при создании движка: все подтягиваемые значения
        (параметры, gcode, пресеты экструдера) применяются к состоянию.
        Вне Orca (или при ошибке) ничего не делает.
        """
        result = self.pull_from_profile()
        if result["ok"]:
            self._apply_pull_result(result)
            # Прошивка из профиля сохраняется в конфиг: при следующем запуске
            # настройка уже предзаполнена (пользователь может её переопределить).
            if result.get("firmware"):
                try:
                    self._plugin.save_config(json.dumps(self._config))
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    # pragma: no cover - вне Orca
                    _LOGGER.warning("Не удалось сохранить прошивку в конфиг: %s", exc)

    def resolved_start_end(self, params: Dict[str, Any]) -> tuple[str, str]:
        """Возвращает (start_gcode, end_gcode) с подставленными плейсхолдерами.

        Приоритет: отредактированный пользователем gcode из params →
        подтянутый из профиля → дефолт из constants.py. Плейсхолдеры
        OrcaSlicer подставляются из параметров.
        """
        start = (
            params.get("startGcode")
            or self._start_gcode
            or default_start_gcode_for(self.firmware)
        )
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
