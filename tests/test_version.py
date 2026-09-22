"""Тривиальный тест: версия пакета читается и соответствует PEP 440."""

import re

from hackretraction import __version__


def test_version_format() -> None:
    """Версия обязана быть валидной по PEP 440 (X.Y.Z)."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__) is not None


def test_version_importable() -> None:
    """Версия доступна и из модуля version."""
    from hackretraction.version import __version__ as module_version

    assert module_version == __version__