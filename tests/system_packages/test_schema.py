def test_versioned_packages_are_available_without_rule_automation(client):
    response = client.get("/api/v1/system-packages/neutral/1")
    assert response.status_code == 200
    assert response.json()["defaults"] == {"fields": [], "resources": [], "skills": []}
    response = client.get("/api/v1/system-packages/dnd-like/1")
    assert response.status_code == 200
    package = response.json()
    assert package["schema_version"] == 1
    assert package["automation"] is None
    assert [field["label"] for field in package["defaults"]["fields"][:6]] == [
        "Сила",
        "Ловкость",
        "Телосложение",
        "Интеллект",
        "Мудрость",
        "Харизма",
    ]
    assert package["defaults"]["resources"][0]["key"] == "hp"
    assert len(package["defaults"]["skills"]) >= 18
    assert client.get("/api/v1/system-packages/unknown/1").status_code == 404
    assert client.get("/api/v1/system-packages/neutral/99").status_code == 404
