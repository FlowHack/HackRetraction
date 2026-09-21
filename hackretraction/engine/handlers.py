"""HandlersMixin: диспетчер сообщений из UI.

Каждое сообщение JS -> Python имеет поле "type"; обработчики называются
_on_<type>. Ответы отправляются через _post (sink, установленный плагином).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..constants import DEFAULT_END_GCODE, DEFAULT_START_GCODE
from ..errors import ExportError, ProfileError
from ..i18n import I18N_COMMENTS
from ..logging import _LOGGER
from .export import ExportMixin
from .generator import generate_gcode
from .params import ParamsMixin, apply_placeholders, parse_gcode

# Инкрементальные шаги: одновременно ненулевым может быть только один.
_STEP_KEYS: tuple[str, ...] = (
    "incrementRetractionspeed",
    "tempIncrementhotend",
    "speedFanIncrement",
)


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

    def _fill_gcode_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Заполняет startGcode/endGcode в params резолвнутыми значениями.

        Пустое поле в params означает «использовать подтянутый из профиля
        или дефолт» — здесь оно заменяется фактическим gcode для UI.
        """
        params = dict(params)
        start, end = self.resolved_start_end(params)
        params["startGcode"] = start
        params["endGcode"] = end
        return params

    def _default_gcode(self, params: Dict[str, Any]) -> tuple[str, str]:
        """Дефолтные start/end gcode с подставленными плейсхолдерами."""
        start = apply_placeholders(DEFAULT_START_GCODE, params)
        end = apply_placeholders(DEFAULT_END_GCODE, params)
        return start, end

    def _on_get_state(self, _message: Dict[str, Any]) -> None:
        params = self._fill_gcode_params(self.get_params())
        start, end = self._default_gcode(params)
        self._post(
            {
                "type": "state",
                "params": params,
                "settings": self.get_settings(),
                "has_gcode": self._gcode is not None,
                "ui": self._ui_bundle(),
                "default_start_gcode": start,
                "default_end_gcode": end,
            }
        )

    # --- Генерация ---

    def _on_generate(self, message: Dict[str, Any]) -> None:
        params = self._resolve_params_for_gen(message.get("params"))
        step_error = self._validate_steps(params)
        if step_error is not None:
            self._post({"type": "status", "key": step_error[0], "params": step_error[1]})
            return
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

    def _validate_steps(
        self, params: Dict[str, Any]
    ) -> Optional[tuple[str, Dict[str, str]]]:
        """Проверка шагов перед генерацией: ровно один ненулевой из трёх.

        Возвращает (ключ статуса, параметры подстановки) при ошибке или None.
        """
        negative = [key for key in _STEP_KEYS if float(params.get(key, 0) or 0) < 0]
        if negative:
            names = ", ".join(self._t("p." + key) for key in negative)
            return "status.step_negative", {"params": names}
        non_zero = [key for key in _STEP_KEYS if float(params.get(key, 0) or 0) != 0]
        if len(non_zero) > 1:
            names = ", ".join(self._t("p." + key) for key in non_zero)
            return "status.step_multiple", {"params": names}
        if not non_zero:
            return "status.step_none", {}
        return None

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
        params = self._fill_gcode_params(self.get_params())
        start, end = self._default_gcode(params)
        self._post(
            {
                "type": "pulled",
                "params": params,
                "extruder": result["extruder"],
                "status": "status.pull_ok",
                "default_start_gcode": start,
                "default_end_gcode": end,
            }
        )

    def _on_reset(self, _message: Dict[str, Any]) -> None:
        self.reset_params()
        self.set_start_end_gcode("", "")
        params = self._fill_gcode_params(self.get_params())
        start, end = self._default_gcode(params)
        self._post(
            {
                "type": "reset",
                "params": params,
                "status": "status.reset_ok",
                "default_start_gcode": start,
                "default_end_gcode": end,
            }
        )

    # --- G-code по умолчанию ---

    def _on_default_gcode(self, message: Dict[str, Any]) -> None:
        """Кнопка «По умолчанию»: подставляет дефолтный gcode в поле."""
        field = str(message.get("field", ""))
        if field not in ("startGcode", "endGcode"):
            _LOGGER.warning("Неизвестное поле gcode: %s", field)
            return
        params = self.get_params()
        default = DEFAULT_START_GCODE if field == "startGcode" else DEFAULT_END_GCODE
        gcode = apply_placeholders(default, params)
        params[field] = gcode
        self.set_params(params)
        self._post(
            {
                "type": "default_gcode_set",
                "field": field,
                "gcode": gcode,
                "params": self.get_params(),
            }
        )

    def _on_recalc_default_gcode(self, message: Dict[str, Any]) -> None:
        """Live-пересчёт дефолтных gcode при изменении размеров стола."""
        params = self.get_params()
        incoming = message.get("params")
        if isinstance(incoming, dict):
            params.update(incoming)
        start, end = self._default_gcode(params)
        self._post(
            {
                "type": "default_gcode_updated",
                "start_gcode": start,
                "end_gcode": end,
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
