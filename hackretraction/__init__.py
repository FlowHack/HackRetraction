"""Пакет HackRetraction — плагин OrcaSlicer для генерации теста ретракции.

Точка входа: @orca.plugin HackRetractionPlugin (register_capabilities).
Вне Orca Slicer (pytest) пакет импортируется с заглушкой.
"""

# pylint: disable=too-few-public-methods

from .version import __version__

__all__ = ["__version__"]

try:
    import orca
except ImportError:
    orca = None

if orca is None:

    class HackRetractionPlugin:  # type: ignore[no-redef]
        """Заглушка плагина вне Orca Slicer (для pytest)."""

        def register_capabilities(self) -> None:
            """Ничего не регистрирует вне Orca."""
            pass

else:
    from .orca_compat import _PAGES_BASE, _SCRIPT_BASE
    from .plugin import HackRetractionTab, HackRetractionWindow

    @orca.plugin
    class HackRetractionPlugin(orca.base):  # type: ignore[no-redef]
        """Точка входа плагина HackRetraction."""

        def register_capabilities(self) -> None:
            """Регистрирует Pages-капабилити (вкладку), иначе Script-fallback.

            Orca сам инстанцирует переданный класс (см. Registry wiki:
            ``orca.register_capability(Cls)``), поэтому передаём классы.
            """
            host = orca
            if _PAGES_BASE is not None:
                host.register_capability(HackRetractionTab)  # type: ignore[attr-defined]
            elif _SCRIPT_BASE is not None:
                host.register_capability(HackRetractionWindow)  # type: ignore[attr-defined]
