"""Минимальный стаб модуля orca для локального QA (pylint/pyright).

Не используется в рантайме Orca Slicer — только для статического анализа
и импорта плагина вне слайсера.
"""

from typing import Any


class PluginType:
    """Тип capability (аналог orca.PluginType в OrcaSlicer)."""

    Unknown = "unknown"
    Pages = "pages"
    Script = "script"
    SlicingPipeline = "slicing_pipeline"
    PrinterConnection = "printer_connection"


class PluginResult:
    """Результат выполнения capability."""

    Success = "success"
    Skipped = "skipped"
    RecoverableError = "recoverable_error"
    FatalError = "fatal_error"


class ExecutionResult:
    """Результат выполнения script-капабилити."""

    def __init__(self, status: str, message: str = "", data: str = "") -> None:
        self.status = status
        self.message = message
        self.data = data

    @staticmethod
    def success(message: str = "", data: str = "") -> "ExecutionResult":
        """Успешный результат."""
        return ExecutionResult(PluginResult.Success, message, data)

    @staticmethod
    def skipped(message: str = "") -> "ExecutionResult":
        """Пропущенное выполнение."""
        return ExecutionResult(PluginResult.Skipped, message)

    @staticmethod
    def failure(status: str, message: str, data: str = "") -> "ExecutionResult":
        """Ошибочное выполнение."""
        return ExecutionResult(status, message, data)


class PythonPluginBase:
    """База с конфигурацией плагина."""

    def get_type(self) -> str:
        """Тип capability (по умолчанию — Unknown)."""
        return PluginType.Unknown

    def get_default_config(self) -> dict:
        """Дефолтная конфигурация."""
        return {}

    def get_config(self) -> str:
        """Сырая JSON-строка конфигурации."""
        return "{}"

    def save_config(self, config: str) -> bool:
        """Сохранение конфигурации."""
        return True

    def has_config_ui(self) -> bool:
        """Наличие кастомного UI настроек."""
        return False

    def get_config_ui(self) -> str:
        """HTML-страница настроек."""
        return ""


class base:
    """Базовый класс пакета плагина."""

    def register_capabilities(self) -> None:
        """Регистрация возможностей."""
        return None


def plugin(cls: Any) -> Any:
    """Декоратор пакета плагина."""
    return cls


def register_capability(cls: Any) -> None:
    """Регистрация capability."""
    return None


from . import host, pages, script  # noqa: E402,F401