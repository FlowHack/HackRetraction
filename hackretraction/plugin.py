"""Плагин HackRetraction: Script-капабилити, открывающее окно генератора.

Пользователь открывает диалог Plugins -> Run; execute() создаёт немодальное
окно через orca.host.ui.create_window. Все настройки — внутри окна
(шестерёнка), поэтому has_config_ui() возвращает False.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from .config import DEFAULT_CONFIG
from .logging import _LOGGER
from .orca_compat import orca, _SCRIPT_BASE
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


class HackRetractionWindow(_ConfigMixin, _SCRIPT_BASE):  # type: ignore[name-defined]
    """Script-плагин: окно генератора теста ретракции."""

    _win: Optional[Any] = None
    _engine: Optional[_HackRetractionEngine] = None

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

    # --- Движок ---

    def _ensure_engine(self) -> _HackRetractionEngine:
        if self._engine is None:
            self._engine = _HackRetractionEngine(self)
            self._engine.set_post_sink(self._make_post_sink())
        return self._engine

    def _make_post_sink(self) -> Callable[[Dict[str, Any]], None]:
        def sink(payload: Dict[str, Any]) -> None:
            self._window_post(payload)

        return sink

    def _window_post(self, payload: Dict[str, Any]) -> None:
        if self._win is not None and self._win.is_open():
            self._win.post(payload)

    def _t(self, key: str, **params: object) -> str:
        return self._ensure_engine()._t(key, **params)