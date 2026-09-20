"""ExportMixin: сохранение сгенерированного gcode в файл по пути пользователя.

Путь вводит пользователь в UI. Запись вне data_dir() проходит через
CPython-аудит Orca (Yes/No при первом обращении, ответ запоминается).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..constants import DEFAULT_GCODE_FILENAME
from ..errors import ExportError
from ..logging import _LOGGER
from ..paths import STORAGE_DIR, atomic_write_text
from .core import CoreMixin


class ExportMixin(CoreMixin):
    """Экспорт gcode: сохранение по пути и путь по умолчанию."""

    def save_gcode(self, path: str) -> str:
        """Сохраняет последний сгенерированный gcode в path. Возвращает путь."""
        gcode = self._gcode
        if not gcode:
            raise ExportError("GCODE ещё не сгенерирован")
        target = Path(path).expanduser()
        try:
            atomic_write_text(target, gcode)
        except OSError as exc:
            raise ExportError(f"Не удалось записать файл: {exc}") from exc
        return str(target)

    def default_export_path(self) -> str:
        """Путь по умолчанию для поля сохранения (в разрешённой зоне)."""
        return str(STORAGE_DIR / DEFAULT_GCODE_FILENAME)