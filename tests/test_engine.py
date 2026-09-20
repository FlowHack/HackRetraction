"""Тесты движка HackRetraction: парсинг, плейсхолдеры, диспетчер, экспорт."""

import os
import tempfile

import pytest

from hackretraction.engine import _HackRetractionEngine
from hackretraction.engine.generator import generate_gcode
from hackretraction.engine.params import apply_placeholders, parse_gcode
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