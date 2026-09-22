"""Исключения плагина HackRetraction."""


class HackRetractionError(Exception):
    """Базовое исключение плагина."""


class ConfigError(HackRetractionError):
    """Ошибка конфигурации плагина."""


class ProfileError(HackRetractionError):
    """Ошибка подтягивания параметров из профиля принтера."""


class GenerationError(HackRetractionError):
    """Ошибка генерации gcode."""


class ExportError(HackRetractionError):
    """Ошибка сохранения gcode в файл."""
