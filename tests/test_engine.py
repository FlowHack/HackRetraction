"""Тесты движка HackRetraction: парсинг, плейсхолдеры, диспетчер, экспорт."""

import os
import tempfile

import pytest

from hackretraction.constants import DEFAULT_PARAMS
from hackretraction.engine import _HackRetractionEngine
from hackretraction.engine.generator import generate_gcode
from hackretraction.engine.params import _parse_printable_area, apply_placeholders, parse_gcode
from hackretraction.errors import ExportError, ProfileError


def _engine():
    return _HackRetractionEngine(None)


def _generate(engine, params=None):
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "generate", "params": params})
    return messages[-1]


def _full_params(**overrides):
    """DEFAULT_PARAMS с заполненными None-полями (эквивалент pull из профиля).

    После п.9 подтягиваемые поля по умолчанию None — для тестов генерации
    нужен полный набор значений, как после успешного pull_from_profile.
    """
    params = {
        "startRetractiondistance": 0.5,
        "incrementRetractiondistance": 0.5,
        "startRetractionspeed": 10.0,
        "incrementRetractionspeed": 10.0,
        "tempStarthotend": 210,
        "tempIncrementhotend": 0,
        "tempBed": 50,
        "speedFan": 40,
        "speedFanIncrement": 0,
        "layerHeight": 0.2,
        "printSpeed": 40.0,
        "speedTravel": 100.0,
        "nozzleDiameter": 0.4,
        "filamentDiameter": 1.75,
        "extrusionMultiplier": 1.0,
        "dimensionX": 220,
        "dimensionY": 220,
        "layersTest": 25,
        "NumTests": 15,
        "startGcode": "",
        "endGcode": "",
    }
    params.update(overrides)
    return params


def test_parse_gcode_roundtrip_en():
    """Сгенерированный gcode (en) парсится обратно в те же параметры."""
    engine = _engine()
    overrides = {
        "dimensionX": 250.0, "dimensionY": 210.0,
        "startRetractiondistance": 0.8, "incrementRetractiondistance": 0.1,
        "startRetractionspeed": 5.0, "incrementRetractionspeed": 2.0,
        "printSpeed": 70.0, "tempStarthotend": 232.0, "tempIncrementhotend": 0.0,
        "tempBed": 80.0, "speedFan": 40.0, "speedFanIncrement": 0.0,
        "nozzleDiameter": 0.4, "layerHeight": 0.2, "filamentDiameter": 1.75,
        "extrusionMultiplier": 0.97, "layersTest": 25.0, "NumTests": 15.0,
    }
    params = _full_params(**overrides)
    msg = _generate(engine, params)
    parsed = parse_gcode(msg["gcode"])
    # parse_gcode возвращает только числовые ключи секции «All inputs»
    for key, value in overrides.items():
        assert parsed[key] == pytest.approx(value, abs=1e-6), key


def test_parse_gcode_ru_comments():
    """Парсер не зависит от языка комментариев gcode."""
    engine = _engine()
    engine._config["comment_lang"] = "ru"
    params = _full_params(NumTests=3, layersTest=5)
    msg = _generate(engine, params)
    parsed = parse_gcode(msg["gcode"])
    assert parsed["NumTests"] == pytest.approx(3)
    assert parsed["layersTest"] == pytest.approx(5)


def test_parse_gcode_missing_section():
    """Нет секции All inputs -> ProfileError."""
    with pytest.raises(ProfileError):
        parse_gcode("G28\nG1 X0")


def test_parse_gcode_incomplete_section():
    """Неполная секция -> ProfileError."""
    gcode = ";All inputs\n;Dimension X \t\t\t\t\t 220\n"
    with pytest.raises(ProfileError):
        parse_gcode(gcode)


def test_apply_placeholders():
    """Подстановка плейсхолдеров из параметров."""
    params = {"dimensionX": 320.0, "dimensionY": 220.0, "tempBed": 80.0}
    out = apply_placeholders(
        "M190 S[bed_temperature_initial_layer_single]\n"
        "G1 X{print_bed_max[0]*0.5-50} Y{print_bed_max[1]}",
        params,
    )
    assert "M190 S80" in out
    assert "X110" in out
    assert "Y220" in out


def test_handle_generate_sets_gcode():
    """После generate движок хранит gcode и отдаёт статистику."""
    engine = _engine()
    params = _full_params(NumTests=5, layersTest=10)
    msg = _generate(engine, params)
    assert msg["type"] == "generated"
    assert msg["stats"]["tests"] == 5
    assert msg["stats"]["layers"] == 10
    assert engine._gcode is not None


def test_handle_reset():
    """Reset возвращает параметры к дефолтам."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.set_params({"NumTests": 99})
    engine.handle_message({"type": "reset"})
    msg = messages[-1]
    assert msg["type"] == "reset"
    assert msg["params"]["NumTests"] == 15


def test_handle_settings():
    """Сохранение настроек обновляет конфиг и отдаёт settings_saved."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "settings", "settings": {"theme": "dark", "language": "ru"}})
    msg = messages[-1]
    assert msg["type"] == "settings_saved"
    assert msg["settings"]["theme"] == "dark"
    assert msg["settings"]["language"] == "ru"


def test_handle_pull_outside_orca_fails():
    """Вне Orca pull не ломается и сообщает о неудаче."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "pull"})
    msg = messages[-1]
    assert msg["type"] == "status"
    assert msg["key"] == "status.pull_fail"


def test_save_gcode(tmp_path):
    """save_gcode пишет файл и возвращает путь."""
    engine = _engine()
    _generate(engine, _full_params())
    target = str(tmp_path / "out.gcode")
    saved = engine.save_gcode(target)
    assert saved == target
    with open(target, encoding="utf-8") as f:
        assert f.read() == engine._gcode


def test_save_gcode_without_generation():
    """Без сгенерированного gcode -> ExportError."""
    engine = _engine()
    with pytest.raises(ExportError):
        engine.save_gcode("/tmp/out.gcode")


def test_unknown_message_logs_only():
    """Неизвестный тип сообщения не роняет движок."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "nonexistent"})
    assert messages == []


def test_get_state_includes_gcode():
    """state отдаёт резолвнутые gcode и дефолты для кнопки «По умолчанию»."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "get_state"})
    msg = messages[-1]
    assert msg["type"] == "state"
    assert "startGcode" in msg["params"]
    assert "endGcode" in msg["params"]
    assert msg["params"]["startGcode"] == msg["default_start_gcode"]
    assert msg["params"]["endGcode"] == msg["default_end_gcode"]
    assert "M190" in msg["params"]["startGcode"]
    assert "M104" in msg["params"]["endGcode"]


def test_get_state_resolves_placeholders():
    """Дефолтный gcode в state подставляет размеры стола из параметров."""
    engine = _engine()
    engine.set_params({"dimensionX": 320.0, "dimensionY": 220.0})
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "get_state"})
    msg = messages[-1]
    assert "X110" in msg["default_start_gcode"]
    assert "Y220" in msg["default_end_gcode"]


def test_default_gcode_button():
    """Кнопка «По умолчанию» подставляет дефолтный gcode в поле."""
    engine = _engine()
    engine.set_params({"dimensionX": 250.0})
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "default_gcode", "field": "startGcode"})
    msg = messages[-1]
    assert msg["type"] == "default_gcode_set"
    assert msg["field"] == "startGcode"
    assert "M190" in msg["gcode"]
    assert msg["params"]["startGcode"] == msg["gcode"]
    # Регрессия: второе gcode-поле не должно пропадать (быть пустым)
    assert msg["params"]["endGcode"] != ""
    assert "M104" in msg["params"]["endGcode"]


def test_default_gcode_keeps_other_field():
    """Кнопка «По умолчанию» на одном поле не затирает другое."""
    engine = _engine()
    engine.set_params({"dimensionX": 250.0})
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "default_gcode", "field": "endGcode"})
    msg = messages[-1]
    assert msg["type"] == "default_gcode_set"
    assert msg["field"] == "endGcode"
    assert "M104" in msg["gcode"]
    assert msg["params"]["endGcode"] == msg["gcode"]
    assert msg["params"]["startGcode"] != ""
    assert "M190" in msg["params"]["startGcode"]


def test_default_gcode_unknown_field_logs_only():
    """Неизвестное поле gcode не роняет движок."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "default_gcode", "field": "bogus"})
    assert messages == []


def test_recalc_default_gcode():
    """Live-пересчёт дефолтов при смене размеров стола."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message(
        {"type": "recalc_default_gcode", "params": {"dimensionX": 320.0, "dimensionY": 220.0}}
    )
    msg = messages[-1]
    assert msg["type"] == "default_gcode_updated"
    assert "X110" in msg["start_gcode"]
    assert "Y220" in msg["end_gcode"]


def test_generate_uses_edited_gcode():
    """Отредактированный пользователем gcode попадает в генерацию."""
    engine = _engine()
    params = _full_params(
        NumTests=3,
        layersTest=5,
        startGcode="G28 ; мой старт",
    )
    msg = _generate(engine, params)
    assert "G28 ; мой старт" in msg["gcode"]


def test_resolved_start_end_priority():
    """Приоритет: params > подтянутый из профиля > дефолт."""
    engine = _engine()
    engine.set_start_end_gcode("G28 ; профиль", "M84 ; профиль")
    params = engine.get_params()
    start, end = engine.resolved_start_end(params)
    assert start == "G28 ; профиль"
    assert end == "M84 ; профиль"
    params["startGcode"] = "G28 ; пользователь"
    start, _ = engine.resolved_start_end(params)
    assert start == "G28 ; пользователь"


def test_parse_printable_area_string():
    """printable_area строкой: '0x0,325x0,325x325,0x325' -> (325, 325)."""
    assert _parse_printable_area("0x0,325x0,325x325,0x325") == (325.0, 325.0)


def test_parse_printable_area_list():
    """printable_area списком (как в JSON-профилях Orca)."""
    area = ["0x0", "325x0", "325x325", "0x325"]
    assert _parse_printable_area(area) == (325.0, 325.0)


def test_parse_printable_area_invalid():
    """Мусорные значения printable_area -> None."""
    assert _parse_printable_area(None) is None
    assert _parse_printable_area("0x0,0x0,0x0,0x0") is None
    assert _parse_printable_area("abc") is None
    assert _parse_printable_area(42) is None


def test_extruder_presets_direct():
    """Пресет direct: старт 1.0/шаг 0.1, скорость 5.0/шаг 2.0."""
    from hackretraction.constants import EXTRUDER_PRESETS

    preset = EXTRUDER_PRESETS["direct"]
    assert preset["startRetractiondistance"] == 1.0
    assert preset["incrementRetractiondistance"] == 0.1
    assert preset["startRetractionspeed"] == 5.0
    assert preset["incrementRetractionspeed"] == 2.0


def test_extruder_presets_bowden():
    """Пресет bowden: классические значения втягивания (эталон генератора).

    DEFAULT_PARAMS больше не хранит эти значения (None до подтяжки) —
    сравниваем с зафиксированными значениями пресета.
    """
    from hackretraction.constants import EXTRUDER_PRESETS

    preset = EXTRUDER_PRESETS["bowden"]
    assert preset["startRetractiondistance"] == 0.5
    assert preset["incrementRetractiondistance"] == 0.5
    assert preset["startRetractionspeed"] == 10.0
    assert preset["incrementRetractionspeed"] == 10.0


def test_handle_reset_outside_orca_defaults():
    """Reset вне Orca: всё к дефолтам, gcode-поля — дефолтные."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.set_params({"NumTests": 99, "startRetractiondistance": 3.0})
    engine.handle_message({"type": "reset"})
    msg = messages[-1]
    assert msg["type"] == "reset"
    assert msg["params"]["NumTests"] == 15
    # Подтягиваемое поле вне Orca не подтянулось — остаётся пустым (None).
    assert msg["params"]["startRetractiondistance"] is None
    assert msg["params"]["startGcode"] == msg["default_start_gcode"]


class _FakeValue:
    """Обёртка значения пресета Orca (getattr(value, 'value', value))."""

    def __init__(self, value):
        self.value = value


class _FakeBundle:
    """Мок preset_bundle: merged-конфиг с ключами профиля."""

    def __init__(self, values):
        self._values = values

    def full_config_value(self, key):
        return self._values.get(key, _FakeValue(None))


class _FakeHost:
    def __init__(self, values):
        self._bundle = _FakeBundle(values)

    def preset_bundle(self):
        return self._bundle


def _fake_orca(values):
    """Подменяет orca в params.py фейковым хостом с preset_bundle."""
    import hackretraction.engine.params as params_mod

    class _FakeOrca:
        host = _FakeHost(values)

    return params_mod, _FakeOrca()


def test_pull_normalizes_newlines(monkeypatch):
    """Подтянутый gcode нормализует литеральные \\n в переносы строк."""
    params_mod, fake = _fake_orca(
        {
            "machine_start_gcode": "M400 ; Очистка буфера\\nM220 S100",
            "machine_end_gcode": "M84 X Y E\\nM104 S0",
            "nozzle_diameter": _FakeValue(0.4),
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    result = engine.pull_from_profile()
    assert result["ok"] is True
    assert result["start_gcode"] == "M400 ; Очистка буфера\nM220 S100"
    assert result["end_gcode"] == "M84 X Y E\nM104 S0"
    assert result["params"]["dimensionX"] == 325.0
    assert result["params"]["dimensionY"] == 325.0
    assert result["params"]["nozzleDiameter"] == 0.4


def test_auto_pull_applies_on_init(monkeypatch):
    """При создании движка параметры подтягиваются из профиля автоматически."""
    params_mod, fake = _fake_orca(
        {
            "machine_start_gcode": "M400 ; Очистка буфера\\nM220 S100",
            "machine_end_gcode": "M84 X Y E\\nM104 S0",
            "nozzle_diameter": _FakeValue(0.4),
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
            "extruder_type": "Direct Drive",
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    params = engine.get_params()
    assert params["dimensionX"] == 325.0
    assert params["dimensionY"] == 325.0
    assert params["nozzleDiameter"] == 0.4
    # пресет direct: старт 1.0, шаг 0.1, скорость 5.0, шаг 2.0
    assert params["startRetractiondistance"] == 1.0
    assert params["incrementRetractiondistance"] == 0.1
    assert params["startRetractionspeed"] == 5.0
    assert params["incrementRetractionspeed"] == 2.0
    # gcode подтянут и нормализован
    start, end = engine.get_start_end_gcode()
    assert start == "M400 ; Очистка буфера\nM220 S100"
    assert end == "M84 X Y E\nM104 S0"


def test_pull_from_profile_strings_and_arrays(monkeypatch):
    """Значения профиля строками/массивами строк (как в реальных JSON Orca)."""
    params_mod, fake = _fake_orca(
        {
            "nozzle_temperature": ["232"],
            "hot_plate_temp": ["80"],
            "fan_min_speed": ["30"],
            "fan_max_speed": ["80"],
            "outer_wall_speed": "30",
            "travel_speed": "200",
            "layer_height": "0.2",
            "filament_flow_ratio": ["0.97"],
            "nozzle_diameter": ["0.4"],
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    result = engine.pull_from_profile()
    assert result["ok"] is True
    params = result["params"]
    assert params["nozzleDiameter"] == 0.4
    assert params["layerHeight"] == 0.2
    assert params["extrusionMultiplier"] == 0.97
    assert params["speedTravel"] == 200.0
    assert params["printSpeed"] == 30.0
    assert params["tempStarthotend"] == 232.0
    assert params["tempBed"] == 80.0
    assert params["speedFan"] == 55.0
    assert params["dimensionX"] == 325.0
    assert params["dimensionY"] == 325.0


def test_pull_from_profile_percent_and_multi_extruder(monkeypatch):
    """Проценты ('85%') и multi-extruder ('0.4;0.2;0.6') нормализуются."""
    params_mod, fake = _fake_orca(
        {
            "fan_min_speed": "0%",
            "fan_max_speed": "85%",
            "nozzle_diameter": "0.4;0.2;0.6;0.8;1.0",
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    result = engine.pull_from_profile()
    assert result["ok"] is True
    assert result["params"]["nozzleDiameter"] == 0.4
    assert result["params"]["speedFan"] == 42.5


class _FakePreset:
    """Мок пресета Orca: name + config_value (с поддержкой inherits)."""

    def __init__(self, name, values, inherits=""):
        self.name = name
        self._values = values
        self._inherits = inherits

    def config_value(self, key):
        if key == "inherits":
            return _FakeValue(self._inherits)
        return _FakeValue(self._values.get(key, None))


class _FakeCollection:
    """Мок коллекции пресетов (printers/filaments/prints)."""

    def __init__(self, presets, selected_name):
        self._presets = {p.name: p for p in presets}
        self._selected = selected_name

    def get_selected_preset(self):
        return self._presets.get(self._selected)

    def find_preset(self, name):
        return self._presets.get(name)


class _FakeChainBundle:
    """Мок preset_bundle с коллекциями для резервного прохода по цепочке."""

    def __init__(self, values, collections):
        self._values = values
        self.printers = collections.get("printers")
        self.filaments = collections.get("filaments")
        self.prints = collections.get("prints")

    def full_config_value(self, key):
        return _FakeValue(self._values.get(key, None))


def test_pull_chain_fallback(monkeypatch):
    """Резервный проход по цепочке наследования находит значение в родителе."""
    params_mod, fake = _fake_orca({})
    # merged-конфиг пуст, но в цепочке пресетов значение есть
    base = _FakePreset("Base", {"outer_wall_speed": "30", "travel_speed": "200"})
    user = _FakePreset("User", {"layer_height": "0.2"}, inherits="Base")
    bundle = _FakeChainBundle(
        {},
        {"prints": _FakeCollection([base, user], "User")},
    )
    fake.host._bundle = bundle
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    result = engine.pull_from_profile()
    assert result["ok"] is True
    assert result["params"]["printSpeed"] == 30.0
    assert result["params"]["speedTravel"] == 200.0
    assert result["params"]["layerHeight"] == 0.2


def test_pull_chain_child_overrides_parent(monkeypatch):
    """Дочерний пресет перекрывает значение родителя в цепочке."""
    params_mod, fake = _fake_orca({})
    base = _FakePreset("Base", {"outer_wall_speed": "30"})
    user = _FakePreset("User", {"outer_wall_speed": "45"}, inherits="Base")
    bundle = _FakeChainBundle(
        {},
        {"prints": _FakeCollection([base, user], "User")},
    )
    fake.host._bundle = bundle
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    result = engine.pull_from_profile()
    assert result["ok"] is True
    assert result["params"]["printSpeed"] == 45.0


# --- Пункты 6-10: None-дефолты, recommended, удаление кнопки pull ---


def test_default_params_none_for_pull_fields():
    """Подтягиваемые поля по умолчанию пусты (None), тестовые — с дефолтами."""
    assert DEFAULT_PARAMS["layersTest"] == 25
    assert DEFAULT_PARAMS["NumTests"] == 15
    assert DEFAULT_PARAMS["startGcode"] == ""
    assert DEFAULT_PARAMS["endGcode"] == ""
    for key in (
        "startRetractiondistance", "incrementRetractiondistance",
        "startRetractionspeed", "incrementRetractionspeed",
        "tempStarthotend", "tempIncrementhotend", "tempBed",
        "speedFan", "speedFanIncrement", "layerHeight", "printSpeed",
        "speedTravel", "nozzleDiameter", "filamentDiameter",
        "extrusionMultiplier", "dimensionX", "dimensionY",
    ):
        assert DEFAULT_PARAMS[key] is None, key


def test_param_steps_fine_increment():
    """Пункт 6: шаг стрелочек layerHeight/filamentDiameter = 0.01."""
    from hackretraction.constants import PARAM_STEPS

    assert PARAM_STEPS["layerHeight"] == 0.01
    assert PARAM_STEPS["filamentDiameter"] == 0.01


def test_set_params_empty_numeric_stores_none():
    """Пустые/None числовые значения сохраняются как None (без warning)."""
    engine = _engine()
    engine.set_params({"layerHeight": None, "speedTravel": "", "tempBed": 80})
    params = engine.get_params()
    assert params["layerHeight"] is None
    assert params["speedTravel"] is None
    assert params["tempBed"] == 80.0


def test_get_state_includes_recommended():
    """Пункт 7: state содержит рекомендуемые значения (для кнопок сброса)."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "get_state"})
    msg = messages[-1]
    assert msg["type"] == "state"
    assert "recommended" in msg
    assert isinstance(msg["recommended"], dict)


def test_handle_reset_includes_recommended():
    """Пункт 7: reset содержит рекомендуемые значения."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "reset"})
    msg = messages[-1]
    assert msg["type"] == "reset"
    assert "recommended" in msg
    assert isinstance(msg["recommended"], dict)


def test_recommended_after_pull(monkeypatch):
    """Пункт 7: recommended = подтянутые параметры + пресет экструдера."""
    params_mod, fake = _fake_orca(
        {
            "nozzle_diameter": _FakeValue(0.4),
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
            "extruder_type": "Direct Drive",
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    rec = engine.get_recommended()
    # пресет direct поверх подтянутого
    assert rec["startRetractiondistance"] == 1.0
    assert rec["incrementRetractiondistance"] == 0.1
    assert rec["dimensionX"] == 325.0


def test_ui_has_no_pull_button():
    """Пункт 8: кнопка «Подтянуть параметры» удалена из HTML и JS."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "hackretraction" / "ui"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert 'id="btn-pull"' not in html
    assert '"btn-pull"' not in js


def test_generate_tolerates_empty_step_triple():
    """Пункт 5 самопроверки: генерация не падает на пустых полях тройки.

    Два из трёх полей тройки пусты (None) — генератор трактует их как 0,
    валидация их не блокирует (проверяет только _validate_steps).
    """
    engine = _engine()
    params = _full_params(
        incrementRetractionspeed=2.0,
        tempIncrementhotend=None,
        speedFanIncrement=None,
    )
    msg = _generate(engine, params)
    assert msg["type"] == "generated"


# --- Пункты 11-16: прошивка, кнопки gcode-полей, мгновенное применение ---


def test_default_start_gcode_for_firmware():
    """Пункт 11: строка карты стола зависит от прошивки."""
    from hackretraction.constants import default_start_gcode_for

    marlin = default_start_gcode_for("marlin")
    assert "M420 S1 Z10" in marlin
    klipper = default_start_gcode_for("klipper")
    assert "BED_MESH_PROFILE LOAD=default" in klipper
    assert "M420" not in klipper
    rrf = default_start_gcode_for("reprapfirmware")
    assert "G29 S1" in rrf
    assert "M420" not in rrf
    repetier = default_start_gcode_for("repetier")
    assert "M420" not in repetier
    # Неизвестная прошивка — как Marlin (строка остаётся).
    assert "M420" in default_start_gcode_for("bogus")


def test_pull_firmware_from_flavor(monkeypatch):
    """Пункт 11: gcode_flavor из профиля маппится в нашу прошивку."""
    params_mod, fake = _fake_orca(
        {
            "gcode_flavor": _FakeValue("marlin2"),
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    result = engine.pull_from_profile()
    assert result["ok"] is True
    assert result["firmware"] == "marlin"


def test_auto_pull_sets_firmware_config(monkeypatch):
    """Пункт 11: при старте прошивка из профиля попадает в конфиг."""
    params_mod, fake = _fake_orca(
        {
            "gcode_flavor": _FakeValue("klipper"),
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    assert engine.firmware == "klipper"


def test_default_gcode_firmware_aware():
    """Пункт 12: кнопка «Рекомендованный» учитывает прошивку."""
    engine = _engine()
    engine.save_settings({"firmware": "klipper"})
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "default_gcode", "field": "startGcode"})
    msg = messages[-1]
    assert msg["type"] == "default_gcode_set"
    assert "BED_MESH_PROFILE LOAD=default" in msg["gcode"]
    assert "M420" not in msg["gcode"]


def test_settings_reapply_keeps_user_edits(monkeypatch):
    """Пункт 11: смена настроек пересчитывает рекомендуемые значения,
    но пользовательские правки полей сохраняются."""
    params_mod, fake = _fake_orca(
        {
            "nozzle_diameter": _FakeValue(0.4),
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
            "extruder_type": "Direct Drive",
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()  # auto-pull: dimensionX=325, пресет direct
    form = engine.get_params()
    form["tempBed"] = 999.0  # правка пользователя
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message(
        {"type": "settings", "settings": {"theme": "dark"}, "params": form}
    )
    msg = messages[-1]
    assert msg["type"] == "settings_saved"
    params = engine.get_params()
    assert params["tempBed"] == 999.0  # правка сохранена
    assert params["dimensionX"] == 325.0  # нетронутое поле пересчитано
    assert params["startRetractiondistance"] == 1.0  # пресет direct


def test_settings_firmware_change_updates_default_gcode():
    """Пункт 11: смена прошивки пересчитывает дефолтный gcode."""
    engine = _engine()
    engine.save_settings({"firmware": "marlin"})
    messages = []
    engine.set_post_sink(messages.append)
    # Поле равно старому дефолту (M420) — после смены прошивки резолвнется
    # в новый дефолт (вне Orca pull не работает, gcode-поле сбрасывается).
    form = engine.get_params()
    form["startGcode"] = engine._default_gcode(form)[0]
    engine.handle_message(
        {"type": "settings", "settings": {"firmware": "klipper"}, "params": form}
    )
    msg = messages[-1]
    assert msg["type"] == "settings_saved"
    params = engine.get_params()
    assert params["startGcode"] == ""
    start, _ = engine.resolved_start_end(params)
    assert "BED_MESH_PROFILE LOAD=default" in start


def test_pull_gcode_button(monkeypatch):
    """Пункт 13: «Подтянуть значение» подтягивает gcode из профиля."""
    params_mod, fake = _fake_orca(
        {
            "machine_start_gcode": "M400 ; Очистка буфера\\nM220 S100",
            "machine_end_gcode": "M84 X Y E\\nM104 S0",
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "pull_gcode", "field": "startGcode"})
    msg = messages[-1]
    assert msg["type"] == "gcode_pulled"
    assert msg["gcode"] == "M400 ; Очистка буфера\nM220 S100"
    assert msg["params"]["startGcode"] == msg["gcode"]


def test_pull_gcode_empty_profile(monkeypatch):
    """Пункт 13: пустой gcode в профиле → поле очищается."""
    params_mod, fake = _fake_orca(
        {
            "machine_start_gcode": "",
            "printable_area": ["0x0", "325x0", "325x325", "0x325"],
        }
    )
    monkeypatch.setattr(params_mod, "orca", fake)
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "pull_gcode", "field": "startGcode"})
    msg = messages[-1]
    assert msg["type"] == "gcode_pulled"
    assert msg["gcode"] == ""


def test_pull_gcode_outside_orca_fails():
    """Пункт 13: вне Orca подтяжка gcode сообщает о неудаче."""
    engine = _engine()
    messages = []
    engine.set_post_sink(messages.append)
    engine.handle_message({"type": "pull_gcode", "field": "startGcode"})
    msg = messages[-1]
    assert msg["type"] == "status"
    assert msg["key"] == "status.pull_fail"


def test_ui_gcode_buttons_present():
    """Пункты 12-13: в UI есть кнопки «Рекомендованный», «Подтянуть значение»
    и ⟳ возврата; тултип Settings у кнопки настроек убран."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "hackretraction" / "ui"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert 'id="btn-settings"' in html
    assert 'title="Settings"' not in html
    assert "data-pull-gcode" in js
    assert "data-default-gcode" in js
    assert "t.default_gcode" in js
    assert "set-firmware" in html
    assert "set-firmware" in js