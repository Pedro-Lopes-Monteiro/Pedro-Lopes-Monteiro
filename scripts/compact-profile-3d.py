#!/usr/bin/env python3
"""Rebuild the night-rainbow city at a shallower ground angle.

yoshi389111/github-profile-3d-contrib cannot hide the radar or the language
donut, and its isometric angle is hardcoded to 30° (ANGLE in
src/create-3d-contrib.ts). Rotating that finished drawing in 2D leans the
walls over with the ground, so the buildings collapse into a flat ribbon.

This script drops the two charts, reads each bar's footprint and height out
of the generated SVG, and redraws the faces with the generator's own
projection at --angle degrees. Walls stay vertical. Smaller angles lay the
week strip closer to horizontal while the contribution height stays put.
Night-rainbow classes and the contribution line are unchanged.

    python3 scripts/compact-profile-3d.py --angle 14
"""

from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
# ANGLE and the 1280px canvas in github-profile-3d-contrib.
SOURCE_ANGLE = 30.0
CANVAS_WIDTH = 1280.0
DX = CANVAS_WIDTH / 64.0

FUNC_RE = re.compile(r"([A-Za-z]+)\s*\(([^)]*)\)")
NUM_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "profile-3d-contrib" / "profile-night-rainbow.svg"
DEFAULT_OUTPUT = ROOT / "profile-3d-contrib" / "profile-night-rainbow-compact.svg"
# Middle of the candidates Pedro is comparing (8, 14, 20). Not a final pick.
DEFAULT_ANGLE = 14.0


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
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]]


def skew_x(deg: float) -> list[list[float]]:
    tangent = math.tan(math.radians(deg))
    return [[1.0, tangent, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def skew_y(deg: float) -> list[list[float]]:
    tangent = math.tan(math.radians(deg))
    return [[1.0, 0.0, 0.0], [tangent, 1.0, 0.0], [0.0, 0.0, 1.0]]


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


def fmt(value: float) -> str:
    """Match github-profile-3d-contrib's toFixed(2), without trailing zeros."""
    rounded = float(f"{value:.2f}")
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


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


def projection(angle: float) -> dict[str, float]:
    """Face metrics from create-3d-contrib.ts at an arbitrary ANGLE."""
    dy = DX * math.tan(math.radians(angle))
    dxx = DX * 0.9
    dyy = dy * 0.9
    scale_side = math.hypot(dxx, dyy) / dxx
    # atan(dxx / 2 / dyy) in degrees, same as the generator's atan().
    skew_x = math.degrees(math.atan((dxx / 2.0) / dyy))
    top_scale_y = (2.0 * dyy) / dxx
    return {
        "dy": dy,
        "dxx": dxx,
        "dyy": dyy,
        "scale_side": scale_side,
        "skew_x": skew_x,
        "top_scale_y": top_scale_y,
    }


def bar_parts(bar: ET.Element) -> tuple[ET.Element, ET.Element, ET.Element]:
    rects = [node for node in list(bar) if local(node.tag) == "rect"]
    if len(rects) != 3:
        raise SystemExit("Expected each contribution bar to have a top, left, and right face.")
    return rects[0], rects[1], rects[2]


def ground_of(bar: ET.Element, source: dict[str, float]) -> tuple[float, float, float]:
    tx_ty = numbers(bar.get("transform") or "")
    if len(tx_ty) < 2:
        raise SystemExit(f"Bar is missing a translate: {bar.get('transform')}")
    _, left, _ = bar_parts(bar)
    height_attr = float(left.get("height") or 0)
    cal_height = height_attr * source["scale_side"]
    if cal_height < 3.05:
        cal_height = 3.0
    base_x = tx_ty[0]
    base_y = tx_ty[1] + cal_height
    return base_x, base_y, cal_height


def rewrite_bar(
    bar: ET.Element,
    angle: float,
    base_x: float,
    base_y: float,
    cal_height: float,
    metrics: dict[str, float],
) -> None:
    top, left, right = bar_parts(bar)
    stub = cal_height if cal_height <= 3.05 else 3.0
    side_h = float(f"{cal_height / metrics['scale_side']:.2f}")
    stub_h = float(f"{stub / metrics['scale_side']:.2f}")
    top_y = base_y - cal_height

    top.set(
        "transform",
        f"skewY({fmt(-angle)}) skewX({fmt(metrics['skew_x'])}) "
        f"scale(1 {fmt(metrics['top_scale_y'])})",
    )
    side_scale = f"scale(1 {fmt(metrics['scale_side'])})"
    left.set("transform", f"skewY({fmt(angle)}) {side_scale}")
    left.set("height", fmt(side_h))
    right.set(
        "transform",
        f"translate({fmt(metrics['dxx'])} {fmt(metrics['dyy'])}) "
        f"skewY({fmt(-angle)}) {side_scale}",
    )
    right.set("height", fmt(side_h))
    bar.set("transform", f"translate({fmt(base_x)} {fmt(top_y)})")

    for face in (left, right):
        for child in list(face):
            if local(child.tag) == "animate" and child.get("attributeName") == "height":
                child.set("values", f"{fmt(stub_h)};{fmt(side_h)}")
    for child in list(bar):
        if local(child.tag) != "animateTransform":
            continue
        child.set(
            "values",
            f"{fmt(base_x)} {fmt(base_y - stub)};{fmt(base_x)} {fmt(top_y)}",
        )


def reproject_city(city: ET.Element, angle: float) -> None:
    source = projection(SOURCE_ANGLE)
    target = projection(angle)
    # Scale only the ground's Y. Bar height is not multiplied, so walls stay tall.
    y_scale = target["dy"] / source["dy"]
    for bar in list(city):
        if local(bar.tag) != "g":
            continue
        base_x, base_y, cal_height = ground_of(bar, source)
        rewrite_bar(bar, angle, base_x, base_y * y_scale, cal_height, target)


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
            width = float(node.get("width") or 0)
            height = float(node.get("height") or 0)
            matrix = mul(bar_matrix, parse_transform(node.get("transform")))
            for px, py in ((x, y), (x + width, y), (x + width, y + height), (x, y + height)):
                points.append(apply(matrix, px, py))
    if not points:
        raise SystemExit("The contribution city has no bars to measure.")
    return points


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


def compact(source: Path, dest: Path, angle: float) -> tuple[float, float]:
    if not 4.0 <= angle <= 30.0:
        raise SystemExit("--angle must be between 4 and 30 degrees.")
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(source)
    root = tree.getroot()
    city, footer, removable = find_groups(root)
    for node in removable:
        root.remove(node)

    reproject_city(city, angle)
    points = city_points(city)
    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_x = max(x for x, _ in points)
    max_y = max(y for _, y in points)

    pad_x = 20.0
    pad_top = 32.0
    pad_bottom = 52.0
    shift_x = pad_x - min_x
    shift_y = pad_top - min_y
    city_w = max_x - min_x
    city_h = max_y - min_y
    width = max(city_w + pad_x * 2, 720.0)
    height = pad_top + city_h + pad_bottom

    city.set("transform", f"translate({fmt(shift_x)} {fmt(shift_y)})")

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
    text = dest.read_text(encoding="utf-8")
    if "xmlns=" not in text:
        text = text.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
        dest.write_text(text, encoding="utf-8")
    return width, height


def parse_args(argv: list[str]) -> tuple[float, Path, Path]:
    angle = DEFAULT_ANGLE
    paths: list[Path] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--angle":
            if index + 1 >= len(argv):
                raise SystemExit("--angle needs a number of degrees, for example --angle 14")
            angle = float(argv[index + 1])
            index += 2
            continue
        paths.append(Path(token))
        index += 1
    source = paths[0] if paths else DEFAULT_INPUT
    dest = paths[1] if len(paths) > 1 else DEFAULT_OUTPUT
    return angle, source, dest


def main() -> None:
    angle, source, dest = parse_args(sys.argv[1:])
    if not source.is_file():
        raise SystemExit(f"Missing generated SVG: {source}")
    width, height = compact(source, dest, angle)
    print(f"wrote {dest} angle={angle:g} ({width:.1f} x {height:.1f})")


if __name__ == "__main__":
    main()
