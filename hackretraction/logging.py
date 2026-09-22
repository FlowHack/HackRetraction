"""Логирование плагина HackRetraction.

Лог пишется в stderr, который Orca Slicer перенаправляет в
data_dir()/log/python_*.log. Прямых файловых операций нет.
"""

import logging
import sys

_LOGGER = logging.getLogger("hackretraction")

if not _LOGGER.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    _LOGGER.addHandler(_handler)
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False
