"""Пач метаданных собранного wheel под требования Orca Slicer.

PEP 508 запрещает пробелы в ``project.name``, поэтому setuptools пишет в
METADATA имя ``HackRetraction``. Orca Slicer показывает в диалоге плагинов
ровно ``METADATA -> Name`` и ``METADATA -> Author``, поэтому скрипт
переписывает заголовок ``Name`` на человекочитаемый ``HackRetraction`` и
обновляет хеш METADATA в RECORD.

Запуск: ``python tools/patch_wheel.py dist/hackretraction-*.whl``.
"""
from __future__ import annotations

import base64
import hashlib
import sys
import zipfile
from pathlib import Path

# Человекочитаемое имя плагина, отображаемое в диалоге плагинов Orca.
DISPLAY_NAME = "HackRetraction"

# Имя импортируемого пакета. Orca выбирает пакет по Import-Name в приоритете
# над нормализованным Name, поэтому задаём его явно: это снимает зависимость
# отображения (Name с пробелом) от разрешения пакета.
IMPORT_NAME = "hackretraction"


def _record_row(archive_path: str, data: bytes) -> str:
    """Строка RECORD для файла: путь, sha256 в base64 без padding и размер."""
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return f"{archive_path},sha256={digest.decode('ascii')},{len(data)}"


def patch_wheel(wheel: Path) -> None:
    """Переписывает METADATA (Name) и синхронизирует RECORD внутри wheel."""
    with zipfile.ZipFile(wheel) as archive:
        items = {info.filename: archive.read(info.filename) for info in archive.infolist()}

    meta_path = next((n for n in items if n.endswith(".dist-info/METADATA")), None)
    record_path = next((n for n in items if n.endswith(".dist-info/RECORD")), None)
    if meta_path is None or record_path is None:
        raise SystemExit(f"{wheel.name}: не найдены METADATA или RECORD")

    dist_infos = {n.split(".dist-info/", 1)[0] for n in items if ".dist-info/" in n}
    if len(dist_infos) != 1:
        raise SystemExit(
            f"{wheel.name}: ожидается ровно один .dist-info, найдено {len(dist_infos)}"
        )

    meta_lines = items[meta_path].decode("utf-8").splitlines()
    name_found = False
    for index, line in enumerate(meta_lines):
        if line.startswith("Name:"):
            meta_lines[index] = f"Name: {DISPLAY_NAME}"
            name_found = True
            break
    if not name_found:
        raise SystemExit(f"{wheel.name}: в METADATA отсутствует заголовок Name")

    if not any(line.startswith("Import-Name:") for line in meta_lines):
        insert_at = next(
            (i for i, line in enumerate(meta_lines) if line.startswith("Name:")),
            0,
        ) + 1
        meta_lines.insert(insert_at, f"Import-Name: {IMPORT_NAME}")

    items[meta_path] = ("\n".join(meta_lines) + "\n").encode("utf-8")

    record_lines = items[record_path].decode("utf-8").splitlines()
    for index, line in enumerate(record_lines):
        if line.split(",", 1)[0] == meta_path:
            record_lines[index] = _record_row(meta_path, items[meta_path])
            break
    items[record_path] = ("\n".join(record_lines) + "\n").encode("utf-8")

    temp = wheel.with_name(wheel.name + ".tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in items.items():
            archive.writestr(path, data)
    temp.replace(wheel)
    print(f"Патч METADATA применён: {wheel.name} -> Name: {DISPLAY_NAME}")


def main(argv: list[str]) -> int:
    """Точка входа: патчит переданные wheel или все из dist/."""
    targets = [Path(arg) for arg in argv[1:]]
    if not targets:
        targets = sorted(Path("dist").glob("*.whl"))
    if not targets:
        print("Нет wheel для обработки", file=sys.stderr)
        return 1
    for wheel in targets:
        patch_wheel(wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))