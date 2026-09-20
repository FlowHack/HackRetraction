"""Пути плагина HackRetraction.

Единственная разрешённая зона записи — data_dir() Orca Slicer
(поднимаемся от __file__ до папки orca_plugins). Вне Orca (pytest,
разработка) используется fallback — родительская папка пакета.
"""

import os
from pathlib import Path

from .logging import _LOGGER


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Атомарная запись текста: временный файл + os.replace."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _find_data_dir() -> Path | None:
    """Поднимается от __file__ до папки orca_plugins, возвращает её родителя."""
    for parent in Path(__file__).resolve().parents:
        if parent.name == "orca_plugins":
            return parent.parent
    return None


def _prepare_storage_dir(raw_dir: Path | None, fallback_dir: Path) -> Path:
    """Создаёт папку хранения; при ошибке — fallback (режим разработки)."""
    if raw_dir is None:
        return fallback_dir
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        return raw_dir
    except OSError as exc:
        _LOGGER.warning("Не удалось создать %s: %s; fallback %s", raw_dir, exc, fallback_dir)
        return fallback_dir


def data_dir() -> Path | None:
    """Корень данных Orca Slicer (родитель orca_plugins) или None вне Orca."""
    return _find_data_dir()


# Папка хранения плагина: data_dir()/hackretraction или родитель пакета.
_raw_data_dir = _find_data_dir()
STORAGE_DIR = _prepare_storage_dir(
    _raw_data_dir / "hackretraction" if _raw_data_dir else None,
    Path(__file__).resolve().parent.parent,
)

# Файл состояния (последние параметры, настройки UI).
STATE_FILE = STORAGE_DIR / "state.json"