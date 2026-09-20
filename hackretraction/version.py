"""Единый источник версии плагина HackRetraction.

Версия меняется ТОЛЬКО здесь. ``pyproject.toml`` читает её через
``[tool.setuptools.dynamic] version = { attr = ... }``, а тег релиза ``vX.Y.Z``
обязан совпадать с ``__version__``.
"""

__version__ = "0.1.0"
