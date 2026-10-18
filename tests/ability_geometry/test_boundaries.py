import math
from uuid import uuid4

import pytest


@pytest.mark.parametrize(
    "shape,parameters,direction,points",
    [
        (
            "circle",
            {"radius": 10},
            None,
            [(10, 0, True), (0, -10, True), (10.00001, 0, False), (0, 0, True)],
        ),
        (
            "radius",
            {"radius": 10},
            None,
            [(10, 0, True), (-10, 0, True), (0, 10.00001, False), (0, 0, True)],
        ),
        (
            "cone",
            {"length": 10, "angle": 90},
            {"x": 0, "y": 10},
            [
                (-5, 5, True),
                (0, 10, True),
                (0, -0.00001, False),
                (-5.00001, 5, False),
                (0, 0, True),
                (0, 10.00001, False),
            ],
        ),
        (
            "line",
            {"length": 10, "width": 4},
            {"x": 10, "y": 0},
            [
                (0, -2, True),
                (10, 2, True),
                (10.00001, 0, False),
                (0, -2.00001, False),
                (-0.00001, 0, False),
            ],
        ),
        (
            "cube",
            {"length": 10},
            {"x": 10, "y": 10},
            [
                (0, math.sqrt(50), True),
                (-math.sqrt(50), 0, True),
                (math.sqrt(50) + 0.00001, 0, False),
                (0, 0, True),
            ],
        ),
    ],
)
@pytest.mark.asyncio
async def test_public_shape_boundary_fixtures(table, shape, parameters, direction, points):
    await table.execute("scene.create", {"name": "Fixtures"})
    await table.execute("scene.grid", {"snap_enabled": False, "unit_size": 64})
    ability = str(uuid4())
    await table.execute(
        "card.create",
        {
            "card": {
                "name": "Fixture card",
                "owner_participant_id": str(table.player.id),
                "abilities": [
                    {
                        "id": ability,
                        "name": shape,
                        "geometry": {
                            "shape": shape,
                            "origin": "point",
                            "units": "фут",
                            **parameters,
                        },
                    }
                ],
            }
        },
    )
    card = (await table.client.get(table.url + "/cards")).json()["cards"][0]
    for index, (x, y, _) in enumerate(points):
        await table.execute(
            "item.create", {"name": str(index), "x": x - 1, "y": y - 1, "width": 2, "height": 2}
        )
    table.actor = table.player
    payload = {"card_id": card["id"], "ability_id": ability, "origin": {"x": 0, "y": 0}}
    if direction:
        payload["direction"] = direction
    _, result = await table.execute("ability.present", payload)
    assert result.status == "accepted", result
    projection = (await table.client.get(table.url + "/scene")).json()
    affected = set(projection["ability_presentations"][0]["affected_item_ids"])
    affected_names = {item["name"] for item in projection["items"] if item["id"] in affected}
    assert affected_names == {str(index) for index, (_, _, hit) in enumerate(points) if hit}
