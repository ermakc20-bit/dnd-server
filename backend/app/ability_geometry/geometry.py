import math

from app.ability_geometry.models import PresentedGeometry

TOLERANCE = 1e-7  # Fixed world-pixel tolerance; closed boundaries, no game-system rules.


def includes(geometry: PresentedGeometry, x: float, y: float) -> bool:
    dx, dy = x - geometry.origin.x, y - geometry.origin.y
    distance = math.hypot(dx, dy)
    if geometry.shape in {"circle", "radius"}:
        return distance <= geometry.radius + TOLERANCE
    c, s = math.cos(geometry.rotation), math.sin(geometry.rotation)
    forward, sideways = dx * c + dy * s, -dx * s + dy * c
    if geometry.shape == "cone":
        if distance > geometry.length + TOLERANCE:
            return False
        if distance <= TOLERANCE or geometry.angle == 360:
            return True
        # Angular tolerance is derived from a fixed spatial tolerance.
        angle = abs(math.atan2(sideways, forward))
        return angle <= math.radians(geometry.angle / 2) + TOLERANCE / distance
    if geometry.shape == "line":
        return (
            -TOLERANCE <= forward <= geometry.length + TOLERANCE
            and abs(sideways) <= geometry.width / 2 + TOLERANCE
        )
    return max(abs(forward), abs(sideways)) <= geometry.length / 2 + TOLERANCE
