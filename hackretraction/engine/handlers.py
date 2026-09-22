"""HandlersMixin: диспетчер сообщений из UI.

Каждое сообщение JS -> Python имеет поле "type"; обработчики называются
_on_<type>. Ответы отправляются через _post (sink, установленный плагином).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..constants import (
    DEFAULT_END_GCODE,
    DEFAULT_PARAMS,
    EXTRUDER_PRESETS,
    default_start_gcode_for,
)
from ..errors import ExportError, ProfileError
from ..i18n import I18N_COMMENTS
from ..logging import _LOGGER
from .core import _STRING_PARAM_KEYS
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
        """Дефолтные start/end gcode с подставленными плейсхолдерами.

        Стартовый gcode зависит от прошивки принтера (строка карты стола).
        """
        start = apply_placeholders(default_start_gcode_for(self.firmware), params)
        end = apply_placeholders(DEFAULT_END_GCODE, params)
        return start, end

    def _on_get_state(self, _message: Dict[str, Any]) -> None:
        params = self._fill_gcode_params(self.get_params())
        start, end = self._default_gcode(params)
        self._post(
            {
                "type": "state",
                "params": params,
                "recommended": self.get_recommended(),
                "settings": self.get_settings(),
                "has_gcode": self._gcode is not None,
                "ui": self._ui_bundle(),
                "default_start_gcode": start,
                "default_end_gcode": end,
            }
        )

    # --- Генерация ---

    def _on_generate(self, message: Dict[str, Any]) -> None:
        incoming = message.get("params")
        empty_field = self._validate_numeric_fields(incoming)
        if empty_field is not None:
            self._post(
                {
                    "type": "status",
                    "key": "status.field_empty",
                    "params": {"field": empty_field},
                }
            )
            return
        params = self._resolve_params_for_gen(incoming)
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

    def _validate_numeric_fields(self, incoming: Any) -> Optional[str]:
        """Проверяет входящие из JS параметры перед генерацией.

        Все числовые ключи DEFAULT_PARAMS обязаны присутствовать и
        конвертироваться в float — пустые поля JS в params не отправляет.
        Возвращает ключ первого проблемного поля или None.
        """
        if not isinstance(incoming, dict):
            return None
        for key in DEFAULT_PARAMS:
            if key in _STRING_PARAM_KEYS:
                continue
            # Поля тройки (инкременты) проверяются отдельно в _validate_steps:
            # они могут быть пустыми (по умолчанию только одно заполнено).
            if key in _STEP_KEYS:
                continue
            value = incoming.get(key)
            if value is None or str(value).strip() == "":
                return key
            try:
                float(value)
            except (TypeError, ValueError):
                return key
        return None

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
        self._apply_pull_result(result)
        params = self._fill_gcode_params(self.get_params())
        start, end = self._default_gcode(params)
        self._post(
            {
                "type": "pulled",
                "params": params,
                "recommended": self.get_recommended(),
                "extruder": result["extruder"],
                "status": "status.pull_ok",
                "default_start_gcode": start,
                "default_end_gcode": end,
            }
        )

    def _on_reset(self, _message: Dict[str, Any]) -> None:
        """Сброс: подтягиваемые из профиля значения — заново из профиля,
        остальные — к дефолтам. Если профиль недоступен — всё к дефолтам."""
        result = self.pull_from_profile()
        params = dict(DEFAULT_PARAMS)
        if result["ok"]:
            params.update(result["params"])
            self.apply_extruder_presets(params, result["extruder"])
            self.set_start_end_gcode(result["start_gcode"], result["end_gcode"])
        else:
            self.set_start_end_gcode("", "")
        self.set_params(params)
        self._recommended = self._compute_recommended(result) if result["ok"] else {}
        params = self._fill_gcode_params(self.get_params())
        start, end = self._default_gcode(params)
        self._post(
            {
                "type": "reset",
                "params": params,
                "recommended": self.get_recommended(),
                "status": "status.reset_ok",
                "default_start_gcode": start,
                "default_end_gcode": end,
            }
        )

    # --- G-code по умолчанию ---

    def _on_default_gcode(self, message: Dict[str, Any]) -> None:
        """Кнопка «Рекомендованный»: подставляет дефолтный gcode в поле.

        Входящие params (текущие значения формы из JS) — база для подстановки
        плейсхолдеров; заменяется ТОЛЬКО целевое поле. Соседнее gcode-поле
        заполняется дефолтом, только если оно пустое — пользовательский ввод
        в нём сохраняется. Дефолтный стартовый gcode зависит от прошивки.
        """
        field = str(message.get("field", ""))
        if field not in ("startGcode", "endGcode"):
            _LOGGER.warning("Неизвестное поле gcode: %s", field)
            return
        incoming = message.get("params")
        if not isinstance(incoming, dict):
            incoming = self.get_params()
        else:
            # База — состояние движка, поверх — значения формы из JS: так
            # плейсхолдеры не упадут, если какое-то поле формы пустое.
            incoming = {**self.get_params(), **incoming}
        default = (
            default_start_gcode_for(self.firmware)
            if field == "startGcode"
            else DEFAULT_END_GCODE
        )
        incoming[field] = apply_placeholders(default, incoming)
        # Соседнее gcode-поле: дефолт только если оно пустое/отсутствует,
        # иначе пользовательский ввод сохраняется.
        other = "endGcode" if field == "startGcode" else "startGcode"
        if not incoming.get(other):
            other_default = (
                DEFAULT_END_GCODE
                if other == "endGcode"
                else default_start_gcode_for(self.firmware)
            )
            incoming[other] = apply_placeholders(other_default, incoming)
        self.set_params(incoming)
        self._post(
            {
                "type": "default_gcode_set",
                "field": field,
                "gcode": incoming[field],
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
        """Сохранение настроек + мгновенное применение.

        После смены настроек пересчитываются рекомендуемые значения и
        дефолтные gcode; поля, не изменённые пользователем, обновляются.
        При смене прошивки gcode-поля, равные старому дефолту, сбрасываются —
        они резолвнутся в новый дефолт (см. _reapply_recommended).
        """
        settings = message.get("settings", {})
        incoming = message.get("params")
        old_firmware = self.firmware
        ok = self.save_settings(settings)
        # gcode-поля, не тронутые пользователем (равны старому дефолту),
        # сбрасываем: после смены прошивки они резолвнутся в новый дефолт.
        if isinstance(incoming, dict) and self.firmware != old_firmware:
            base = {**self.get_params(), **incoming}
            old_start = apply_placeholders(default_start_gcode_for(old_firmware), base)
            old_end = apply_placeholders(DEFAULT_END_GCODE, base)
            if incoming.get("startGcode") == old_start:
                incoming["startGcode"] = ""
            if incoming.get("endGcode") == old_end:
                incoming["endGcode"] = ""
        # Без params (например, закрытие окна настроек без изменений) ничего
        # не пересчитываем: иначе все поля обнулятся (reapply с None).
        if isinstance(incoming, dict):
            self._reapply_recommended(incoming)
        self._post(
            {
                "type": "settings_saved",
                "ok": ok,
                "settings": self.get_settings(),
            }
        )

    def _reapply_recommended(self, incoming: Any) -> None:
        """Пересчитывает рекомендуемые значения после смены настроек.

        Поля, не изменённые пользователем (равны старому рекомендуемому),
        обновляются новыми подтянутыми значениями; пользовательские правки
        сохраняются. Вне Orca — только пересчёт дефолтных gcode.
        """
        result = self.pull_from_profile()
        params: Dict[str, Any] = {}
        for key in DEFAULT_PARAMS:
            if isinstance(incoming, dict) and key in incoming:
                params[key] = incoming[key]
            else:
                params[key] = None
        if result["ok"]:
            rec = self._recommended
            for key, value in result["params"].items():
                if params.get(key) == rec.get(key):
                    params[key] = value
            preset = EXTRUDER_PRESETS.get(result["extruder"])
            if preset:
                for key, value in preset.items():
                    if params.get(key) == rec.get(key):
                        params[key] = value
            self.set_start_end_gcode(result["start_gcode"], result["end_gcode"])
            self._recommended = self._compute_recommended(result)
        self.set_params(params)

    # --- Подтяжка gcode из профиля в поле ---

    def _on_pull_gcode(self, message: Dict[str, Any]) -> None:
        """Кнопка «Подтянуть значение»: подтягивает gcode из профиля в поле.

        Если в профиле gcode пустой — поле очищается. Плейсхолдеры
        подставляются из текущих значений формы.
        """
        field = str(message.get("field", ""))
        if field not in ("startGcode", "endGcode"):
            _LOGGER.warning("Неизвестное поле gcode: %s", field)
            return
        result = self.pull_from_profile()
        if not result["ok"]:
            self._post({"type": "status", "key": "status.pull_fail"})
            return
        raw = result["start_gcode"] if field == "startGcode" else result["end_gcode"]
        incoming = message.get("params")
        base = (
            {**self.get_params(), **incoming}
            if isinstance(incoming, dict)
            else self.get_params()
        )
        value = apply_placeholders(raw, base) if raw else ""
        params = self.get_params()
        params[field] = value
        self.set_params(params)
        self._post(
            {
                "type": "gcode_pulled",
                "field": field,
                "gcode": value,
                "params": self.get_params(),
            }
        )
