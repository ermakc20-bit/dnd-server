from copy import deepcopy
from typing import Any

from app.cards.models import CardData
from app.scenes.models import SceneFailure

ATTRIBUTES = [
    ("strength", "Сила"),
    ("dexterity", "Ловкость"),
    ("constitution", "Телосложение"),
    ("intelligence", "Интеллект"),
    ("wisdom", "Мудрость"),
    ("charisma", "Харизма"),
]
SKILLS = [
    "Акробатика",
    "Атлетика",
    "Внимательность",
    "Выживание",
    "Выступление",
    "Запугивание",
    "История",
    "Ловкость рук",
    "Магия",
    "Медицина",
    "Обман",
    "Природа",
    "Проницательность",
    "Расследование",
    "Религия",
    "Скрытность",
    "Убеждение",
    "Уход за животными",
]


def get_schema(system_id: str, version: int = 1) -> dict[str, Any]:
    if version != 1 or system_id not in {"neutral", "dnd-like"}:
        raise SceneFailure("package_unavailable", "Версия игрового пакета недоступна", 404)
    fields = []
    resources: list[dict[str, Any]] = []
    skills = []
    if system_id == "dnd-like":
        definitions = [
            *ATTRIBUTES,
            ("armor", "Защита"),
            ("initiative", "Инициатива"),
            ("speed", "Скорость"),
        ]
        definitions += [(f"save_{key}", f"Спасбросок: {label}") for key, label in ATTRIBUTES]
        fields = [
            dict(
                key=key,
                label=label,
                value=10 if index < 6 else 0,
                value_type="number",
                visibility="everyone",
                order=index,
            )
            for index, (key, label) in enumerate(definitions)
        ]
        resources = [
            dict(key="hp", label="Здоровье", current=10, max=10, color=None, visibility="everyone")
        ]
        skills = [
            dict(
                key=f"skill_{index}",
                name=name,
                bonus=0,
                proficient=False,
                description=None,
                visibility="everyone",
            )
            for index, name in enumerate(SKILLS)
        ]
    return deepcopy(
        dict(
            schema_version=1,
            system_id=system_id,
            version=version,
            name="Нейтральный" if system_id == "neutral" else "Приключения · d20",
            automation=None,
            defaults=dict(fields=fields, resources=resources, skills=skills),
        )
    )


def validate_card(data: CardData) -> CardData:
    package = get_schema(data.system_id, data.system_version)
    reserved = {field["key"]: field["value_type"] for field in package["defaults"]["fields"]}
    if any(
        field.key in reserved and field.value_type != reserved[field.key] for field in data.fields
    ):
        raise SceneFailure("invalid_command", "Тип поля не соответствует игровому пакету", 422)
    return data
