"""Loading the files of a site's data directory."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from . import tomlw, yamlite
from .errors import ContentError
from .utils.fs import read_text

_INT = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_FLOAT = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]+\Z")


def load_data_file(path) -> object:
    """Parse one data file, picking the format from its extension.

    CSV and TSV files become a list of dicts keyed by the header row.
    """
    path = Path(path)
    loader = _LOADERS.get(path.suffix.lower())
    if loader is None:
        kind = path.suffix or path.name
        raise ContentError(f"unsupported data file type {kind!r}", path=path)
    try:
        text = read_text(path)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise ContentError(f"cannot read data file: {reason}", path=path) from None
    return loader(text, path)


def load_data_dir(directory) -> dict:
    """Load every data file below ``directory`` into one nested dict.

    ``data/authors.yaml`` ends up under ``"authors"``, ``data/nav/main.json``
    under ``["nav"]["main"]``. A missing directory just gives an empty dict.
    """
    root = Path(directory)
    if not root.is_dir():
        return {}
    return _load_dir(root)


def _load_dir(directory: Path) -> dict:
    data: dict = {}
    sources: dict[str, Path] = {}
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            key, value = entry.name, _load_dir(entry)
        elif entry.suffix.lower() in _LOADERS:
            key, value = entry.stem, load_data_file(entry)
        else:
            continue
        if key in sources:
            other = sources[key].name
            raise ContentError(
                f"data key {key!r} is already provided by {other}", path=entry
            )
        sources[key] = entry
        data[key] = value
    return data


def _load_json(text: str, path: Path):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContentError(
            f"invalid JSON: {exc.msg}", path=path, line=exc.lineno
        ) from None


def _load_yaml(text: str, path: Path):
    try:
        return yamlite.loads(text)
    except yamlite.YamlError as exc:
        raise ContentError(
            f"invalid YAML: {exc.problem}", path=path, line=exc.line
        ) from None


def _load_toml(text: str, path: Path):
    try:
        return tomlw.loads(text)
    except tomlw.TomlError as exc:
        raise ContentError(
            f"invalid TOML: {exc.message}", path=path, line=exc.line
        ) from None


def _load_csv(text: str, path: Path, delimiter: str = ","):
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        header = next(reader, None)
        if header is None:
            return []
        names = [name.strip() for name in header]
        for index, name in enumerate(names, 1):
            if not name:
                raise ContentError(f"column {index} has no name", path=path, line=1)
            if names.index(name) != index - 1:
                raise ContentError(f"duplicate column {name!r}", path=path, line=1)
        rows = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            if len(row) > len(names):
                raise ContentError(
                    f"row has {len(row)} fields but the header only has {len(names)}",
                    path=path,
                    line=reader.line_num,
                )
            # short rows are padded: a trailing empty cell is easy to lose
            row = row + [""] * (len(names) - len(row))
            rows.append({name: _infer(cell) for name, cell in zip(names, row)})
        return rows
    except csv.Error as exc:
        raise ContentError(
            f"malformed table: {exc}", path=path, line=reader.line_num
        ) from None


def _load_tsv(text: str, path: Path):
    return _load_csv(text, path, delimiter="\t")


def _infer(cell: str):
    """Light typing for table cells: numbers, booleans and empty -> None.

    Numbers with leading zeros stay strings, they are usually codes.
    """
    value = cell.strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if _INT.match(value):
        return int(value)
    if _FLOAT.match(value):
        return float(value)
    return value


_LOADERS = {
    ".json": _load_json,
    ".yaml": _load_yaml,
    ".yml": _load_yaml,
    ".toml": _load_toml,
    ".csv": _load_csv,
    ".tsv": _load_tsv,
}
