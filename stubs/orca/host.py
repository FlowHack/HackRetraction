"""Стаб orca.host для локального QA.

Повторяет реальный API: orca.host — модуль с функциями model(),
preset_bundle(), plater() и подмодулем ui.
"""

from typing import Any


class ui:
    """Стаб orca.host.ui."""

    @staticmethod
    def create_window(
        html: str = "",
        title: str = "",
        on_message: Any = None,
        on_close: Any = None,
    ) -> Any:
        """Создание окна."""
        return None


def model() -> Any:
    """Снимок модели на столе."""
    raise NotImplementedError


def preset_bundle() -> Any:
    """Снимок пресетов."""
    raise NotImplementedError


def plater() -> Any:
    """Снимок платера."""
    raise NotImplementedError