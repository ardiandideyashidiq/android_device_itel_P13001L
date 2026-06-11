#!/usr/bin/env python3
#
# Copyright (C) 2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

from __future__ import annotations

import argparse
import sys

from dataclasses import dataclass
from pathlib import Path


DEFAULT_DUMP_ROOT = Path("stock_dump")
TREE_PROP_FILES = (
    Path("configs/properties/system.prop"),
    Path("configs/properties/vendor.prop"),
)
DUMP_SOURCES = (
    ("system", Path("system/system/build.prop")),
    ("product", Path("product/etc/build.prop")),
    ("vendor", Path("vendor/build.prop")),
)
SOURCE_PRIORITY = {
    Path("configs/properties/system.prop"): ("system", "product", "vendor"),
    Path("configs/properties/vendor.prop"): ("vendor", "system", "product"),
}


@dataclass(frozen=True)
class PropertyMatch:
    key: str
    tree_file: Path
    tree_value: str
    source_name: str
    source_file: Path
    stock_value: str

    @property
    def is_mismatch(self) -> bool:
        return self.tree_value != self.stock_value


@dataclass(frozen=True)
class ParsedTreeProps:
    lines: list[str]
    props: dict[str, str]
    line_indexes: dict[str, list[int]]


def parse_prop_lines(path: Path) -> ParsedTreeProps:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    props: dict[str, str] = {}
    line_indexes: dict[str, list[int]] = {}

    for idx, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue

        key, value = raw_line.rstrip("\n").split("=", 1)
        key = key.strip()
        props[key] = value
        line_indexes.setdefault(key, []).append(idx)

    return ParsedTreeProps(lines=lines, props=props, line_indexes=line_indexes)


def parse_prop_values(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue

        key, value = raw_line.split("=", 1)
        props[key.strip()] = value

    return props


def choose_stock_value(
    key: str,
    dump_sources: dict[str, tuple[Path, dict[str, str]]],
    source_order: tuple[str, ...],
) -> tuple[str, Path, str] | None:
    for source_name in source_order:
        source_file, props = dump_sources[source_name]
        if key in props:
            return source_name, source_file, props[key]

    return None


def write_updated_props(
    path: Path,
    lines: list[str],
    line_indexes: dict[str, list[int]],
    updates: dict[str, str],
) -> None:
    if not updates:
        return

    new_lines = list(lines)
    for key, new_value in updates.items():
        for line_idx in line_indexes[key]:
            line = new_lines[line_idx]
            suffix = "\n" if line.endswith("\n") else ""
            new_lines[line_idx] = f"{key}={new_value}{suffix}"

    path.write_text("".join(new_lines), encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare device-tree property files against stock dump props and "
            "optionally apply mismatched values."
        )
    )
    parser.add_argument(
        "--dump-root",
        type=Path,
        default=DEFAULT_DUMP_ROOT,
        help=f"Path to stock dump root (default: {DEFAULT_DUMP_ROOT})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite mismatched values in configs/properties/*.prop",
    )
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    repo_root = Path(__file__).resolve().parent
    dump_root = args.dump_root.resolve()

    missing_sources = [
        dump_root / relative_path for _, relative_path in DUMP_SOURCES
        if not (dump_root / relative_path).is_file()
    ]
    if missing_sources:
        for source in missing_sources:
            print(f"Missing dump property file: {source}", file=sys.stderr)
        return 2

    dump_sources = {
        name: (dump_root / relative_path, parse_prop_values(dump_root / relative_path))
        for name, relative_path in DUMP_SOURCES
    }

    matches: list[PropertyMatch] = []
    unmatched: list[tuple[Path, str, str]] = []
    updates_by_file: dict[Path, dict[str, str]] = {}

    for tree_file in TREE_PROP_FILES:
        tree_path = repo_root / tree_file
        if not tree_path.is_file():
            print(f"Missing tree property file: {tree_path}", file=sys.stderr)
            return 2

        parsed_tree = parse_prop_lines(tree_path)
        file_updates: dict[str, str] = {}

        duplicate_keys = [
            key for key, indexes in parsed_tree.line_indexes.items() if len(indexes) > 1
        ]
        if duplicate_keys:
            print(
                f"Warning: duplicate keys in {tree_file}; using last value for compare: "
                + ", ".join(duplicate_keys),
                file=sys.stderr,
            )

        for key, tree_value in parsed_tree.props.items():
            selected = choose_stock_value(
                key,
                dump_sources,
                SOURCE_PRIORITY[tree_file],
            )
            if selected is None:
                unmatched.append((tree_file, key, tree_value))
                continue

            source_name, source_file, stock_value = selected
            match = PropertyMatch(
                key=key,
                tree_file=tree_file,
                tree_value=tree_value,
                source_name=source_name,
                source_file=source_file,
                stock_value=stock_value,
            )
            matches.append(match)

            if match.is_mismatch:
                file_updates[key] = stock_value

        if args.apply and file_updates:
            write_updated_props(
                tree_path,
                parsed_tree.lines,
                parsed_tree.line_indexes,
                file_updates,
            )

        updates_by_file[tree_file] = file_updates

    mismatches = [match for match in matches if match.is_mismatch]

    for tree_file in TREE_PROP_FILES:
        file_matches = [match for match in mismatches if match.tree_file == tree_file]
        file_unmatched = [item for item in unmatched if item[0] == tree_file]

        print(f"[{tree_file}]")

        if file_matches:
            print("  mismatches:")
            for match in file_matches:
                print(f"    {match.key}")
                print(f"      tree:   {match.tree_value}")
                print(f"      stock:  {match.stock_value}")
                print(
                    "      source: "
                    f"{match.source_name} ({match.source_file.relative_to(dump_root)})"
                )
        else:
            print("  mismatches: none")

        if file_unmatched:
            print("  unmatched:")
            for _, key, tree_value in file_unmatched:
                print(f"    {key}={tree_value}")
        else:
            print("  unmatched: none")

        if args.apply:
            print(f"  applied: {len(updates_by_file[tree_file])}")

        print()

    print(
        "Summary: "
        f"{len(mismatches)} mismatches, "
        f"{len(unmatched)} unmatched, "
        f"{sum(len(updates) for updates in updates_by_file.values()) if args.apply else 0} applied"
    )

    if args.apply:
        return 0

    return 1 if mismatches or unmatched else 0


if __name__ == "__main__":
    sys.exit(main())
