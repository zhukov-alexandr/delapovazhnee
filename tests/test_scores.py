from server.db import get_conn, top_scores


def test_post_score_and_top10_ordering(client):
    for name, score in [("Alice", 30), ("Bob", 50), ("Cara", 10), ("", 40)]:
        assert client.post("/api/score", json={"name": name, "score": score}).status_code == 200
    data = client.get("/api/scores").json()["scores"]
    assert [s["score"] for s in data] == [50, 40, 30, 10]  # highest first
    assert data[1]["name"] == "Аноним"  # empty name defaults


def test_scores_limited_to_10(client):
    for i in range(15):
        client.post("/api/score", json={"name": f"P{i}", "score": i})
    data = client.get("/api/scores").json()["scores"]
    assert len(data) == 10
    assert data[0]["score"] == 14  # only the top 10 survive


def test_negative_score_rejected(client):
    assert client.post("/api/score", json={"name": "x", "score": -1}).status_code == 422


def test_name_trimmed(client, settings):
    client.post("/api/score", json={"name": "  Зина  ", "score": 5})
    rows = top_scores(get_conn(settings.db_path))
    assert rows[0]["name"] == "Зина"


def test_scores_empty_initially(client):
    assert client.get("/api/scores").json() == {"scores": []}
