"""Тесты движка HackRetraction: парсинг, плейсхолдеры, диспетчер, экспорт."""

import os
import tempfile

import pytest

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


def test_parse_gcode_roundtrip_en():
    """Сгенерированный gcode (en) парсится обратно в те же параметры."""
    engine = _engine()
    params = {
        "dimensionX": 250.0, "dimensionY": 210.0,
        "startRetractiondistance": 0.8, "incrementRetractiondistance": 0.1,
        "startRetractionspeed": 5.0, "incrementRetractionspeed": 2.0,
        "printSpeed": 70.0, "tempStarthotend": 232.0, "tempIncrementhotend": 0.0,
        "tempBed": 80.0, "speedFan": 40.0, "speedFanIncrement": 0.0,
        "nozzleDiameter": 0.4, "layerHeight": 0.2, "filamentDiameter": 1.75,
        "extrusionMultiplier": 0.97, "layersTest": 25.0, "NumTests": 15.0,
    }
    msg = _generate(engine, params)
    parsed = parse_gcode(msg["gcode"])
    for key, value in params.items():
        assert parsed[key] == pytest.approx(value, abs=1e-6), key


def test_parse_gcode_ru_comments():
    """Парсер не зависит от языка комментариев gcode."""
    engine = _engine()
    engine._config["comment_lang"] = "ru"
    msg = _generate(engine, {"NumTests": 3, "layersTest": 5})
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
    msg = _generate(engine, {"NumTests": 5, "layersTest": 10})
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
    _generate(engine)
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
    msg = _generate(
        engine,
        {"NumTests": 3, "layersTest": 5, "startGcode": "G28 ; мой старт"},
    )
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
    """Пресет bowden совпадает с дефолтами генератора."""
    from hackretraction.constants import DEFAULT_PARAMS, EXTRUDER_PRESETS

    preset = EXTRUDER_PRESETS["bowden"]
    for key in ("startRetractiondistance", "incrementRetractiondistance",
                "startRetractionspeed", "incrementRetractionspeed"):
        assert preset[key] == DEFAULT_PARAMS[key], key


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
    assert msg["params"]["startRetractiondistance"] == 0.5
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