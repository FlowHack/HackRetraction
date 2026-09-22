"""Движок HackRetraction: _HackRetractionEngine, собранный из миксинов.

Порядок MRO: HandlersMixin -> ParamsMixin -> ExportMixin -> CoreMixin.
"""

from __future__ import annotations

from typing import Any

from .core import CoreMixin
from .export import ExportMixin
from .handlers import HandlersMixin
from .params import ParamsMixin


class _HackRetractionEngine(HandlersMixin, ExportMixin, CoreMixin):
    """Собранный движок: конфиг, параметры, генерация, экспорт, диспетчер."""

    def __init__(self, plugin: Any) -> None:
        self._plugin = plugin
        self._init_core()
        # При старте плагина подтягиваем все доступные параметры из профиля
        # (размеры стола, gcode, пресеты экструдера и т.д.).
        self._auto_pull()
