#!/usr/bin/env python3
"""Turn the night-rainbow 3D profile SVG into a short, wide city.

yoshi389111/github-profile-3d-contrib (see src/type.ts and src/create-svg.ts)
can recolor a chart via SETTING_JSON and can emit radar_contrib_only or
pie_lang_only files, but a full chart always includes the radar and the
language donut. The isometric angle is a hardcoded 30 degrees in
src/create-3d-contrib.ts (ANGLE), with no size or camera setting.

This reads the generated profile-night-rainbow.svg, drops those two charts,
rotates the city by -30 degrees so the week strip runs left to right, and
writes a tight viewBox. The contribution count, stars, forks, and date stay.
"""

from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
# Matches ANGLE in github-profile-3d-contrib src/create-3d-contrib.ts.
ISOMETRIC_ANGLE = 30.0

FUNC_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
NUM_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "profile-3d-contrib" / "profile-night-rainbow.svg"
DEFAULT_OUTPUT = ROOT / "profile-3d-contrib" / "profile-night-rainbow-compact.svg"


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def numbers(text: str) -> list[float]:
    return [float(value) for value in NUM_RE.findall(text)]


def ident() -> list[list[float]]:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [
            a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j]
            for j in range(3)
        ]
        for i in range(3)
    ]


def apply(matrix: list[list[float]], x: float, y: float) -> tuple[float, float]:
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
    )


def translate(tx: float, ty: float) -> list[list[float]]:
    return [[1.0, 0.0, tx], [0.0, 1.0, ty], [0.0, 0.0, 1.0]]


def scale(sx: float, sy: float) -> list[list[float]]:
    return [[sx, 0.0, 0.0], [0.0, sy, 0.0], [0.0, 0.0, 1.0]]


def rotate(deg: float) -> list[list[float]]:
    radians = math.radians(deg)
    c = math.cos(radians)
    s = math.sin(radians)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def skew_x(deg: float) -> list[list[float]]:
    t = math.tan(math.radians(deg))
    return [[1.0, t, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def skew_y(deg: float) -> list[list[float]]:
    t = math.tan(math.radians(deg))
    return [[1.0, 0.0, 0.0], [t, 1.0, 0.0], [0.0, 0.0, 1.0]]


def parse_transform(value: str | None) -> list[list[float]]:
    matrix = ident()
    if not value:
        return matrix
    for name, args in FUNC_RE.findall(value):
        vals = numbers(args)
        name = name.lower()
        if name == "translate":
            tx = vals[0] if vals else 0.0
            ty = vals[1] if len(vals) > 1 else 0.0
            step = translate(tx, ty)
        elif name == "scale":
            sx = vals[0] if vals else 1.0
            sy = vals[1] if len(vals) > 1 else sx
            step = scale(sx, sy)
        elif name == "rotate":
            step = rotate(vals[0] if vals else 0.0)
            if len(vals) >= 3:
                cx, cy = vals[1], vals[2]
                step = mul(mul(translate(cx, cy), step), translate(-cx, -cy))
        elif name == "skewx":
            step = skew_x(vals[0] if vals else 0.0)
        elif name == "skewy":
            step = skew_y(vals[0] if vals else 0.0)
        elif name == "matrix" and len(vals) >= 6:
            a, b, c, d, e, f = vals[:6]
            step = [[a, c, e], [b, d, f], [0.0, 0.0, 1.0]]
        else:
            continue
        matrix = mul(matrix, step)
    return matrix


def class_tokens(element: ET.Element) -> set[str]:
    return set((element.get("class") or "").split())


def has_class(element: ET.Element, name: str) -> bool:
    return any(name in class_tokens(node) for node in element.iter())


def direct_text(element: ET.Element) -> str:
    return (element.text or "").strip()


def find_groups(root: ET.Element) -> tuple[ET.Element, ET.Element, list[ET.Element]]:
    """Return (city, footer, removable charts) among the svg's direct children."""
    city = None
    footer = None
    removable: list[ET.Element] = []
    for child in list(root):
        if local(child.tag) != "g":
            continue
        texts = [direct_text(node) for node in child.iter() if local(node.tag) == "text"]
        if any(text == "contributions" for text in texts):
            footer = child
            continue
        if has_class(child, "radar"):
            removable.append(child)
            continue
        rects = [node for node in child.iter() if local(node.tag) == "rect"]
        paths = [node for node in child.iter() if local(node.tag) == "path"]
        if len(rects) >= 50:
            city = child
        elif paths:
            removable.append(child)
    if city is None or footer is None:
        raise SystemExit(
            "Could not find the contribution city and the footer text in the SVG."
        )
    return city, footer, removable


def city_points(city: ET.Element) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for bar in list(city):
        if local(bar.tag) != "g":
            continue
        bar_matrix = parse_transform(bar.get("transform"))
        for node in list(bar):
            if local(node.tag) != "rect":
                continue
            x = float(node.get("x") or 0)
            y = float(node.get("y") or 0)
            w = float(node.get("width") or 0)
            h = float(node.get("height") or 0)
            matrix = mul(bar_matrix, parse_transform(node.get("transform")))
            for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
                points.append(apply(matrix, px, py))
    if not points:
        raise SystemExit("The contribution city has no bars to measure.")
    return points


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def place_footer(footer: ET.Element, width: float, baseline: float) -> None:
    """Keep the count, stars, forks, and date on the compact canvas."""
    number = None
    label = None
    date = None
    icons: list[ET.Element] = []
    icon_labels: list[ET.Element] = []
    for child in list(footer):
        kind = local(child.tag)
        if kind == "text":
            classes = class_tokens(child)
            content = direct_text(child)
            if "fill-strong" in classes and number is None:
                number = child
            elif content == "contributions" and label is None:
                label = child
            elif "fill-weak" in classes and date is None:
                date = child
            else:
                icon_labels.append(child)
        elif kind == "g":
            icons.append(child)

    if number is not None:
        number.set("x", fmt(148))
        number.set("y", fmt(baseline))
        number.set("text-anchor", "end")
    if label is not None:
        label.set("x", fmt(158))
        label.set("y", fmt(baseline))
        label.set("text-anchor", "start")

    # Star then fork, same order the generator writes them.
    icon_x = (360, 520)
    for index, icon in enumerate(icons[:2]):
        x = icon_x[index] if index < len(icon_x) else 360 + index * 160
        icon.set("transform", f"translate({fmt(x)}, {fmt(baseline - 28)}) scale(2)")
        if index < len(icon_labels):
            icon_labels[index].set("x", fmt(x + 42))
            icon_labels[index].set("y", fmt(baseline))
            icon_labels[index].set("text-anchor", "start")

    if date is not None:
        date.set("x", fmt(width - 16))
        date.set("y", "8")
        date.set("text-anchor", "end")
        date.set("dominant-baseline", "hanging")


def compact(source: Path, dest: Path) -> tuple[float, float]:
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(source)
    root = tree.getroot()
    city, footer, removable = find_groups(root)
    for node in removable:
        root.remove(node)

    rotated = [apply(rotate(-ISOMETRIC_ANGLE), x, y) for x, y in city_points(city)]
    min_x = min(x for x, _ in rotated)
    min_y = min(y for _, y in rotated)
    max_x = max(x for x, _ in rotated)
    max_y = max(y for _, y in rotated)

    pad_x = 20.0
    pad_top = 32.0
    # Room for the 32px contribution line under the city.
    pad_bottom = 52.0
    tx = pad_x - min_x
    ty = pad_top - min_y
    city_w = max_x - min_x
    city_h = max_y - min_y
    width = max(city_w + pad_x * 2, 720.0)
    height = pad_top + city_h + pad_bottom
    if width <= height:
        raise SystemExit(
            f"Compact canvas is not wider than it is tall ({width:.1f}x{height:.1f})."
        )

    city.set("transform", f"translate({fmt(tx)} {fmt(ty)}) rotate({fmt(-ISOMETRIC_ANGLE)})")

    for child in list(root):
        if local(child.tag) == "rect" and "fill-bg" in class_tokens(child):
            child.set("x", "0")
            child.set("y", "0")
            child.set("width", fmt(width))
            child.set("height", fmt(height))

    place_footer(footer, width, pad_top + city_h + 36.0)

    root.set("width", fmt(width))
    root.set("height", fmt(height))
    root.set("viewBox", f"0 0 {fmt(width)} {fmt(height)}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tree.write(dest, encoding="unicode", xml_declaration=False)
    # ElementTree does not write the xmlns when the root already carries the
    # Clark notation and the default namespace is registered; keep the root
    # explicit so renderers accept the file.
    text = dest.read_text(encoding="utf-8")
    if "xmlns=" not in text:
        text = text.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
        dest.write_text(text, encoding="utf-8")
    return width, height


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    if not source.is_file():
        raise SystemExit(f"Missing generated SVG: {source}")
    width, height = compact(source, dest)
    print(f"wrote {dest} ({width:.1f} x {height:.1f})")


if __name__ == "__main__":
    main()
