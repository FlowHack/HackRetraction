"""Совместимость с API Orca Slicer.

Импорт orca опционален: пакет должен импортироваться вне Orca (pytest).
"""

import importlib

try:
    import orca  # type: ignore[import-not-found]
except ImportError:
    orca = None  # type: ignore[assignment]

try:
    import numpy as _np  # type: ignore[import-not-found]
    _HAS_NUMPY = True
except ImportError:
    _np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

# Базовый класс Script-капабилити (окно по кнопке Run в диалоге Plugins).
try:
    _SCRIPT_BASE = getattr(
        importlib.import_module("orca.script"), "ScriptPluginCapabilityBase", None
    )
except (ImportError, AttributeError):
    _SCRIPT_BASE = None
