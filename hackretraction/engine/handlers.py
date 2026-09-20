"""HandlersMixin: диспетчер сообщений из UI.

Каждое сообщение JS -> Python имеет поле "type"; обработчики называются
_on_<type>. Ответы отправляются через _post (sink, установленный плагином).
"""

from __future__ import annotations

from typing import Any, Dict

from ..errors import ExportError, ProfileError
from ..i18n import I18N_COMMENTS
from ..logging import _LOGGER
from .export import ExportMixin
from .generator import generate_gcode
from .params import ParamsMixin, parse_gcode


class HandlersMixin(ParamsMixin, ExportMixin):
    """Обработка сообщений UI: generate/save/pull/reset/load/settings/state."""

    def handle_message(self, message: Dict[str, Any]) -> None:
        """Диспетчер: вызывает _on_<type> или логирует неизвестный тип."""
        msg_type = str(message.get("type", ""))
        handler = getattr(self, f"_on_{msg_type}", None)
        if handler is None:
            _LOGGER.warning("Неизвестный тип сообщения из UI: %s", msg_type)
            return
        try:
            handler(message)  # pylint: disable=not-callable
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Ошибка обработки сообщения %s: %s", msg_type, exc)
            self._post({"type": "error", "message": str(exc)})

    # --- Состояние ---

    def _on_get_state(self, _message: Dict[str, Any]) -> None:
        self._post(
            {
                "type": "state",
                "params": self.get_params(),
                "settings": self.get_settings(),
                "has_gcode": self._gcode is not None,
                "ui": self._ui_bundle(),
            }
        )

    # --- Генерация ---

    def _on_generate(self, message: Dict[str, Any]) -> None:
        params = self._resolve_params_for_gen(message.get("params"))
        start, end = self.resolved_start_end(params)
        comments = I18N_COMMENTS.get(self.comment_lang)
        gcode = generate_gcode(params, start, end, comments)
        self._gcode = gcode
        self._post(
            {
                "type": "generated",
                "gcode": gcode,
                "stats": {
                    "lines": gcode.count("\n"),
                    "tests": int(float(params["NumTests"])),
                    "layers": int(float(params["layersTest"])),
                },
            }
        )

    # --- Экспорт ---

    def _on_save(self, message: Dict[str, Any]) -> None:
        path = str(message.get("path", "")).strip()
        if not path:
            self._post(
                {
                    "type": "status",
                    "key": "status.save_failed",
                    "params": {"error": "empty path"},
                }
            )
            return
        try:
            saved = self.save_gcode(path)
        except ExportError as exc:
            self._post(
                {
                    "type": "status",
                    "key": "status.save_failed",
                    "params": {"error": str(exc)},
                }
            )
            return
        self._post({"type": "status", "key": "status.saved", "params": {"path": saved}})

    # --- Профиль ---

    def _on_pull(self, _message: Dict[str, Any]) -> None:
        result = self.pull_from_profile()
        if not result["ok"]:
            self._post({"type": "status", "key": "status.pull_fail"})
            return
        params = self.get_params()
        params.update(result["params"])
        self.apply_extruder_presets(params, result["extruder"])
        self.set_params(params)
        self.set_start_end_gcode(result["start_gcode"], result["end_gcode"])
        self._post(
            {
                "type": "pulled",
                "params": self.get_params(),
                "extruder": result["extruder"],
                "status": "status.pull_ok",
            }
        )

    def _on_reset(self, _message: Dict[str, Any]) -> None:
        self.reset_params()
        self._post(
            {
                "type": "reset",
                "params": self.get_params(),
                "status": "status.reset_ok",
            }
        )

    # --- Подгрузка ранее сгенерированного gcode ---

    def _on_load_gcode(self, message: Dict[str, Any]) -> None:
        text = str(message.get("gcode", ""))
        try:
            params = parse_gcode(text)
        except ProfileError as exc:
            self._post(
                {
                    "type": "status",
                    "key": "status.load_failed",
                    "params": {"error": str(exc)},
                }
            )
            return
        self.set_params(params)
        self._post({"type": "loaded", "params": self.get_params()})

    # --- Настройки ---

    def _on_settings(self, message: Dict[str, Any]) -> None:
        settings = message.get("settings", {})
        ok = self.save_settings(settings)
        self._post(
            {
                "type": "settings_saved",
                "ok": ok,
                "settings": self.get_settings(),
            }
        )