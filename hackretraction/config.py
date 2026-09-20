"""Конфигурация плагина HackRetraction.

Настройки UI (тема, шрифт, язык) хранятся через официальное API
orca.PythonPluginBase (get_config/save_config).
"""

CONFIG_VERSION = 1

DEFAULT_CONFIG: dict[str, object] = {
    "theme": "auto",  # auto | dark | light
    "font_size": 14,
    "font_style": "system",  # system | mono
    "language": "en",  # en | ru | sr — язык UI
    "comment_lang": "en",  # en | ru | sr — язык комментариев в gcode
}

# Ключи настроек, редактируемых через UI (без секретов).
SETTINGS_KEYS: tuple[str, ...] = (
    "theme", "font_size", "font_style", "language", "comment_lang",
)

# Допустимые значения настроек.
THEMES: tuple[str, ...] = ("auto", "dark", "light")
LANGUAGES: tuple[str, ...] = ("en", "ru", "sr")
FONT_STYLES: tuple[str, ...] = ("system", "mono")
FONT_SIZES: tuple[int, ...] = (12, 13, 14, 15, 16, 18, 20)
