"""Плагин HackRetraction: Pages-капабилити (вкладка) и Script-fallback (окно).

Основной способ запуска — вкладка в главном окне Orca Slicer
(PagesPluginCapabilityBase). Если сборка Orca не поддерживает Pages,
используется Script-капабилити: диалог Plugins -> Run открывает немодальное
окно через orca.host.ui.create_window. Все настройки — внутри окна
(шестерёнка), поэтому has_config_ui() возвращает False.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Callable, Dict, Optional

from .config import DEFAULT_CONFIG
from .logging import _LOGGER
from .orca_compat import orca, _PAGES_BASE, _SCRIPT_BASE
from .paths import STORAGE_DIR, atomic_write_text
from .ui import HTML_PAGE
from .engine import _HackRetractionEngine


class _ConfigMixin:
    """Конфигурация через официальное API orca.PythonPluginBase."""

    def get_default_config(self) -> str:
        return json.dumps(DEFAULT_CONFIG)

    def get_config(self) -> str:
        try:
            raw = super().get_config()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - вне Orca
            return "{}"
        return str(raw) if raw else "{}"

    def save_config(self, config: str) -> bool:
        try:
            super().save_config(config)  # type: ignore[attr-defined]
            return True
        except Exception as exc:  # pragma: no cover - вне Orca
            _LOGGER.error("Не удалось сохранить конфиг: %s", exc)
            return False

    def has_config_ui(self) -> bool:
        return False


class _CapabilityMixin:
    """Общие методы Pages- и Script-капабилити: движок и доставка в UI."""

    _engine: Optional[_HackRetractionEngine] = None

    def _ensure_engine(self) -> _HackRetractionEngine:
        if self._engine is None:
            self._engine = _HackRetractionEngine(self)
            self._engine.set_post_sink(self._make_post_sink())
        return self._engine

    def _make_post_sink(self) -> Callable[[Dict[str, Any]], None]:
        # Для Pages — post_message из базы; для Script-fallback — _window_post.
        return getattr(self, "post_message", self._window_post)

    def _window_post(self, payload: Dict[str, Any]) -> None:
        win = getattr(self, "_win", None)
        if win is not None and win.is_open():
            win.post(payload)

    def _t(self, key: str, **params: object) -> str:
        return self._ensure_engine()._t(key, **params)


# Вне Orca (и в мок-окружении pytest без orca.pages) _PAGES_BASE равен None —
# подставляем object, чтобы класс существовал и импорт пакета не падал.
_TAB_BASE = _PAGES_BASE if _PAGES_BASE is not None else object
_WIN_BASE = _SCRIPT_BASE if _SCRIPT_BASE is not None else object


class HackRetractionTab(_ConfigMixin, _CapabilityMixin, _TAB_BASE):  # type: ignore[misc]
    """Pages-капабилити: вкладка генератора в главном окне Orca Slicer."""

    def get_name(self) -> str:
        return "HackRetraction"

    def get_type(self) -> str:
        """Тип capability — страница (вкладка) интерфейса Orca Slicer.

        Явное значение нужно потому, что встроенная база страниц в некоторых
        сборках OrcaSlicer возвращает ``Unknown``, из-за чего в диалоге
        плагинов колонка «Types» показывает ``unknown`` вместо ``Pages``.
        """
        plugin_type = getattr(orca, "PluginType", None)
        if plugin_type is not None:
            for name in ("Pages", "Page"):
                value: Any = getattr(plugin_type, name, None)
                if value is not None:
                    return value
        getter: Any = getattr(super(), "get_type", None)
        if getter is not None:
            return getter()
        return str(getattr(plugin_type, "Unknown", "Unknown"))

    def get_ui(self) -> str:
        """HTML-содержимое вкладки."""
        self._ensure_engine()
        return HTML_PAGE

    def get_icon(self) -> str:
        """Записывает иконку вкладки в data_dir() и возвращает путь к файлу."""
        try:
            svg = (
                resources.files("hackretraction.ui")
                .joinpath("brand.svg")
                .read_text(encoding="utf-8")
            )
            icon_file = STORAGE_DIR / "tab_icon.svg"
            atomic_write_text(icon_file, svg)
            return str(icon_file)
        except OSError as exc:
            _LOGGER.warning("Не удалось записать иконку вкладки: %s", exc)
            return ""

    def on_message(self, message: Dict[str, Any]) -> None:
        """Обрабатывает сообщение из пользовательского интерфейса вкладки."""
        self._ensure_engine().handle_message(message)


class HackRetractionWindow(_ConfigMixin, _CapabilityMixin, _WIN_BASE):  # type: ignore[misc]
    """Script-плагин: окно генератора теста ретракции (fallback)."""

    _win: Optional[Any] = None

    def get_name(self) -> str:
        return "HackRetraction"

    def execute(self) -> Any:
        """Открывает окно генератора (или сообщает, что оно уже открыто)."""
        host = orca  # type: ignore[assignment]
        if self._win is not None and self._win.is_open():
            return host.ExecutionResult.success(self._t("win.already_open"))  # type: ignore[attr-defined]
        try:
            self._win = host.host.ui.create_window(  # type: ignore[attr-defined]
                html=HTML_PAGE,
                title=self._t("window_title"),
                width=1180,
                height=780,
                on_message=self._on_message,
                on_close=self._on_close,
            )
        except Exception as exc:
            _LOGGER.error("Не удалось открыть окно: %s", exc)
            return host.ExecutionResult.failure(  # type: ignore[attr-defined]
                host.PluginResult.RecoverableError, self._t("win.open_failed")  # type: ignore[attr-defined]
            )
        return host.ExecutionResult.success(self._t("win.opened"))  # type: ignore[attr-defined]

    # --- Обратные вызовы окна ---

    def _on_message(self, message: Dict[str, Any]) -> None:
        self._ensure_engine().handle_message(message)

    def _on_close(self, *_args: Any) -> None:
        self._win = None