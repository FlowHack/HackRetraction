"""Стаб orca.pages для локального QA."""

from typing import Any

from . import PluginType, PythonPluginBase


class PagesPluginCapabilityBase(PythonPluginBase):
    """База pages-капабилити (вкладка в главном окне)."""

    def get_name(self) -> str:
        """Имя вкладки."""
        return ""

    def get_type(self) -> str:
        """Тип capability — страница (вкладка)."""
        return PluginType.Pages

    def get_ui(self) -> str:
        """HTML-страница вкладки."""
        return ""

    def get_icon(self) -> str:
        """Путь к файлу иконки."""
        return ""

    def on_message(self, message: Any) -> None:
        """Обработка сообщения из UI."""
        return None

    def post_message(self, payload: Any) -> None:
        """Отправка payload в UI."""
        return None