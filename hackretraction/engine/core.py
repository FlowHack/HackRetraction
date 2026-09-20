"""CoreMixin: конфигурация, состояние параметров, локализация движка.

Движок HackRetraction — набор миксинов, собранных в engine/__init__.py.
CoreMixin отвечает за конфиг (тема/шрифт/язык), текущие параметры,
стартовый/конечный gcode и локализацию строк.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from ..config import DEFAULT_CONFIG, SETTINGS_KEYS
from ..constants import DEFAULT_PARAMS
from ..i18n import get_text
from ..logging import _LOGGER

# Сигнатура отправки результата в UI (устанавливается плагином).
PostSink = Callable[[Dict[str, Any]], None]


class CoreMixin:
    """Конфигурация и состояние движка."""

    # Ссылка на плагин (устанавливается в __init__ движка).
    _plugin: Any = None

    def _init_core(self) -> None:
        self._config: Dict[str, Any] = {}
        self._config_loaded = False
        self._params: Dict[str, Any] = dict(DEFAULT_PARAMS)
        self._start_gcode = ""
        self._end_gcode = ""
        self._gcode: Optional[str] = None
        self._post_sink: Optional[PostSink] = None

    # --- Конфигурация ---

    @property
    def config(self) -> Dict[str, Any]:
        """Конфиг плагина (тема, шрифт, язык), с дефолтами."""
        if not self._config_loaded:
            self._config = self._load_config()
            self._config_loaded = True
        return self._config

    def _load_config(self) -> Dict[str, Any]:
        raw: Any = None
        try:
            raw = self._plugin.get_config()
        except Exception as exc:  # pragma: no cover - вне Orca
            _LOGGER.warning("Не удалось прочитать конфиг: %s", exc)
        cfg: Dict[str, Any] = {}
        if raw:
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(parsed, dict):
                    cfg = parsed
            except (TypeError, ValueError) as exc:
                _LOGGER.warning("Некорректный конфиг: %s", exc)
        return {**DEFAULT_CONFIG, **cfg}

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Обновляет настройки UI и сохраняет их через API плагина."""
        allowed = {k: v for k, v in settings.items() if k in SETTINGS_KEYS}
        if not allowed:
            return False
        cfg = dict(self.config)
        cfg.update(allowed)
        self._config = cfg
        try:
            self._plugin.save_config(json.dumps(cfg))
            return True
        except Exception as exc:  # pragma: no cover - вне Orca
            _LOGGER.error("Не удалось сохранить конфиг: %s", exc)
            return False

    def get_settings(self) -> Dict[str, Any]:
        """Текущие настройки UI (только редактируемые ключи)."""
        return {k: self.config.get(k) for k in SETTINGS_KEYS}

    # --- Локализация ---

    @property
    def lang(self) -> str:
        return str(self.config.get("language", "en"))

    @property
    def comment_lang(self) -> str:
        return str(self.config.get("comment_lang", "en"))

    def _t(self, key: str, **params: object) -> str:
        return get_text(self.lang, key, **params)

    def _ui_bundle(self) -> Dict[str, Any]:
        """Локализованный бандл для построения формы в JS."""
        from ..i18n import PARAM_SECTIONS, PARAM_TYPES, PARAM_UNITS, I18N_PY

        table = I18N_PY.get(self.lang, I18N_PY["en"])
        return {
            "sections": PARAM_SECTIONS,
            "labels": {k: v for k, v in table.items() if k.startswith("p.")},
            "tips": {k: v for k, v in table.items() if k.startswith("t.")},
            "units": PARAM_UNITS,
            "types": PARAM_TYPES,
            "texts": {k: v for k, v in table.items() if not k.startswith(("p.", "t."))},
        }

    # --- Параметры ---

    def get_params(self) -> Dict[str, Any]:
        return dict(self._params)

    def set_params(self, params: Dict[str, Any]) -> None:
        """Обновляет параметры (числовые — float, customGcode — строка)."""
        for key, value in params.items():
            if key not in DEFAULT_PARAMS:
                continue
            if key == "customGcode":
                self._params[key] = str(value)
            else:
                try:
                    self._params[key] = float(value)
                except (TypeError, ValueError):
                    _LOGGER.warning("Некорректное значение параметра %s: %r", key, value)

    def reset_params(self) -> None:
        self._params = dict(DEFAULT_PARAMS)

    def set_start_end_gcode(self, start: str, end: str) -> None:
        self._start_gcode = start or ""
        self._end_gcode = end or ""

    def get_start_end_gcode(self) -> tuple[str, str]:
        return self._start_gcode, self._end_gcode

    # --- Отправка в UI ---

    def set_post_sink(self, sink: PostSink) -> None:
        self._post_sink = sink

    def _post(self, payload: Dict[str, Any]) -> None:
        if self._post_sink is not None:
            try:
                self._post_sink(payload)
            except Exception as exc:  # pragma: no cover - защита от сбоев UI
                _LOGGER.error("Не удалось отправить сообщение в UI: %s", exc)