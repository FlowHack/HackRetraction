"""Сборка HTML_PAGE из ресурсов ui/ (index.html + style.css + app.js)."""

from __future__ import annotations

from importlib import resources

_UI = resources.files("hackretraction.ui")


def _read(name: str) -> str:
    return _UI.joinpath(name).read_text(encoding="utf-8")


HTML_PAGE = (
    _read("index.html")
    .replace("<!--STYLE-->", _read("style.css"))
    .replace("<!--SCRIPT-->", _read("app.js"))
)
