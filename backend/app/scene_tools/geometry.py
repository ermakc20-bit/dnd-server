import math
from collections.abc import Sequence
from itertools import pairwise
from typing import NamedTuple, Protocol

from app.scene_tools.models import Fog, Point


class Coordinate(Protocol):
    @property
    def x(self) -> float: ...

    @property
    def y(self) -> float: ...


class WorldPoint(NamedTuple):
    # Derived geometry is finite but may exceed the accepted input coordinate bounds.
    x: float
    y: float


def contains(points: Sequence[Coordinate], x: float, y: float) -> bool:
    inside = False
    for a, b in zip(points, [*points[1:], *points[:1]], strict=True):
        cross = (x - a.x) * (b.y - a.y) - (y - a.y) * (b.x - a.x)
        if (
            abs(cross) < 1e-8
            and min(a.x, b.x) <= x <= max(a.x, b.x)
            and min(a.y, b.y) <= y <= max(a.y, b.y)
        ):
            return True
        if (a.y > y) != (b.y > y) and x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x:
            inside = not inside
    return inside


def visible(fog: Fog, x: float, y: float) -> bool:
    return not fog.enabled or any(contains(reveal.points, x, y) for reveal in fog.reveals)


def object_visible(
    fog: Fog, x: float, y: float, width: float, height: float, rotation: float
) -> bool:
    # Require the entire object footprint to be revealed. No hidden token metadata is sent.
    if not fog.enabled:
        return True
    angle = math.radians(rotation)
    cx, cy = x + width / 2, y + height / 2
    corners = [
        WorldPoint(
            x=cx + dx * math.cos(angle) - dy * math.sin(angle),
            y=cy + dx * math.sin(angle) + dy * math.cos(angle),
        )
        for dx, dy in (
            (-width / 2, -height / 2),
            (width / 2, -height / 2),
            (width / 2, height / 2),
            (-width / 2, height / 2),
        )
    ]
    return any(polygon_covers(reveal.points, corners, closed=True) for reveal in fog.reveals)


def segment_covered(polygon: Sequence[Coordinate], a: Coordinate, b: Coordinate) -> bool:
    # Partition at every boundary contact, including vertices and collinear overlaps.
    # Each open interval then has one inside/outside classification.
    dx, dy = b.x - a.x, b.y - a.y
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return contains(polygon, a.x, a.y)
    cuts = {0.0, 1.0}
    for c, d in zip(polygon, [*polygon[1:], *polygon[:1]], strict=True):
        ex, ey = d.x - c.x, d.y - c.y
        offset_x, offset_y = c.x - a.x, c.y - a.y
        denominator = dx * ey - dy * ex
        if denominator != 0:
            t = (offset_x * ey - offset_y * ex) / denominator
            u = (offset_x * dy - offset_y * dx) / denominator
            if -1e-10 <= t <= 1 + 1e-10 and -1e-10 <= u <= 1 + 1e-10:
                cuts.add(max(0.0, min(1.0, t)))
        elif abs(offset_x * dy - offset_y * dx) < 1e-8:
            for point in (c, d):
                t = ((point.x - a.x) * dx + (point.y - a.y) * dy) / length_squared
                if 0 <= t <= 1:
                    cuts.add(t)
    ordered = sorted(cuts)
    return all(
        contains(polygon, a.x + dx * ((left + right) / 2), a.y + dy * ((left + right) / 2))
        for left, right in pairwise(ordered)
    )


def polygon_covers(
    polygon: Sequence[Coordinate], points: Sequence[Coordinate], *, closed: bool = False
) -> bool:
    if not all(contains(polygon, p.x, p.y) for p in points):
        return False
    edges = list(zip(points, [*points[1:], *(points[:1] if closed else [])], strict=False))
    if not all(segment_covered(polygon, a, b) for a, b in edges):
        return False
    if closed:
        # A reveal boundary inside the footprint also excludes an interior region,
        # even when it only contacts the footprint through a polygon vertex.
        for vertex in polygon:
            if contains(points, vertex.x, vertex.y) and not any(
                abs((vertex.x - a.x) * (b.y - a.y) - (vertex.y - a.y) * (b.x - a.x)) < 1e-8
                and min(a.x, b.x) <= vertex.x <= max(a.x, b.x)
                and min(a.y, b.y) <= vertex.y <= max(a.y, b.y)
                for a, b in edges
            ):
                return False
    return True


def path_visible(fog: Fog, points: list[Point]) -> bool:
    return not fog.enabled or any(polygon_covers(reveal.points, points) for reveal in fog.reveals)
