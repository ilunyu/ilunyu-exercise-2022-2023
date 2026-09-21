#!/usr/bin/env python3
"""Build this annual exercise repository as an Android .ilunyupack resource."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from validate_exercises import validate_exercise


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FORMAT = 1
CONTENT_SCHEMA = 1


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: root must be an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def exercise_paths() -> list[Path]:
    return sorted(path for path in ROOT.glob("*.json") if path.name != "resource.json")


def exercise_summary(exercise: dict[str, Any]) -> dict[str, Any]:
    return {
        key: exercise[key]
        for key in ("id", "title", "year", "source", "type", "grade", "number", "score", "month")
        if key in exercise
    }


def read_exercises() -> list[dict[str, Any]]:
    exercises = []
    for path in exercise_paths():
        errors = validate_exercise(path)
        if errors:
            raise ValueError("\n".join(errors))
        exercises.append(read_json(path))
    if not exercises:
        raise ValueError("no exercise JSON files found")
    return exercises


def write_package(output: Path) -> dict[str, Any]:
    config = read_json(ROOT / "resource.json")
    exercises = read_exercises()
    with tempfile.TemporaryDirectory(prefix="ilunyu-package-") as directory:
        build = Path(directory)
        content = build / "content"
        write_json(content / "index.json", {
            "formatVersion": 2,
            "exercises": [exercise_summary(exercise) for exercise in exercises],
        })
        write_json(content / "search.json", {
            "formatVersion": 2,
            "exercises": [
                {**exercise_summary(exercise), "question": exercise.get("question", [])}
                for exercise in exercises
            ],
        })
        for exercise in exercises:
            write_json(content / "items" / f"{exercise['id']}.json", exercise)
        file_hashes = {
            path.relative_to(build).as_posix(): f"sha256:{sha256(path)}"
            for path in sorted(content.rglob("*.json"))
        }
        manifest = {
            "packageFormat": PACKAGE_FORMAT,
            "contentSchema": CONTENT_SCHEMA,
            "packageId": config["packageId"],
            "kind": config["kind"],
            "name": config["name"],
            "versionName": config["versionName"],
            "versionCode": config["versionCode"],
            "minAppVersionCode": config["minAppVersionCode"],
            "sourceRepository": config.get("sourceRepository", ""),
            "license": config.get("license", ""),
            "createdAt": config.get("createdAt", ""),
            "files": file_hashes,
        }
        write_json(build / "manifest.json", manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(build.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(path.relative_to(build).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return {
        "packageId": manifest["packageId"],
        "kind": manifest["kind"],
        "name": manifest["name"],
        "versionName": manifest["versionName"],
        "versionCode": manifest["versionCode"],
        "minAppVersionCode": manifest["minAppVersionCode"],
        "size": output.stat().st_size,
        "sha256": sha256(output),
        "sourceRepository": manifest["sourceRepository"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "resource.ilunyupack")
    parser.add_argument("--release-output", type=Path)
    args = parser.parse_args()
    result = write_package(args.output.resolve())
    release_output = (args.release_output or args.output.parent / "release.json").resolve()
    write_json(release_output, result)
    print(f"Built {args.output}: {result['size']} bytes, sha256 {result['sha256']}")


if __name__ == "__main__":
    main()
