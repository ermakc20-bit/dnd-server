from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=-1000000, le=1000000)
    y: float = Field(ge=-1000000, le=1000000)


class Reveal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[Point] = Field(min_length=3, max_length=32)

    @model_validator(mode="after")
    def area(self) -> "Reveal":
        area = sum(
            a.x * b.y - b.x * a.y
            for a, b in zip(self.points, self.points[1:] + self.points[:1], strict=True)
        )
        if abs(area) < 0.01:
            raise ValueError("Область должна иметь ненулевую площадь")

        def cross(a: Point, b: Point, c: Point) -> float:
            return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)

        edges = list(zip(self.points, self.points[1:] + self.points[:1], strict=True))
        if len({(point.x, point.y) for point in self.points}) != len(self.points):
            raise ValueError("Точки области должны различаться")
        for i, (a, b) in enumerate(edges):
            for j, (c, d) in enumerate(edges):
                if j <= i + 1 or (i == 0 and j == len(edges) - 1):
                    continue
                if cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0:
                    raise ValueError("Границы области не должны пересекаться")
        return self


class Fog(BaseModel):
    enabled: bool = False
    reveals: list[Reveal] = Field(default_factory=list, max_length=100)


class AnnotationData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["line", "arrow", "label"]
    points: list[Point] = Field(min_length=1, max_length=2)
    label: str = Field(default="", max_length=160)
    visibility: Literal["everyone", "gm_only"] = "everyone"

    @model_validator(mode="after")
    def geometry(self) -> "AnnotationData":
        if len(self.points) != (1 if self.kind == "label" else 2):
            raise ValueError("Проверьте точки метки")
        if self.kind == "label" and not self.label.strip():
            raise ValueError("Введите текст метки")
        return self


class Annotation(AnnotationData):
    id: UUID
    owner_participant_id: UUID
    can_edit: bool = False


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnnotationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    annotation_id: UUID


class AnnotationUpdate(AnnotationTarget):
    annotation: AnnotationData
