"""Тест импорта пакета с реальным (мок) модулем orca.

Регрессионный тест: ветка `if orca is None` в __init__.py скрывала ошибки
импорта plugin.py (неверные относительные импорты) от pytest. Здесь пакет
импортируется в изолированном процессе с мок-модулем orca в sys.path.
"""

import os
import subprocess
import sys
from pathlib import Path


def test_plugin_imports_with_real_orca():
    """hackretraction импортируется, когда orca доступен (как в OrcaSlicer)."""
    repo_root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(repo_root / "tests" / "mocks"), str(repo_root / "stubs"), existing) if p
    )
    code = (
        "import hackretraction\n"
        "assert hackretraction.__version__\n"
        "assert hackretraction.HackRetractionPlugin is not None\n"
        "from hackretraction.plugin import HackRetractionWindow\n"
        "assert HackRetractionWindow.get_name(HackRetractionWindow) == 'HackRetraction'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr