from server.db import get_conn, top_scores


def test_post_score_and_top10_ordering(client, save_score):
    for name, score in [("Alice", 30), ("Bob", 50), ("Cara", 10), ("", 40)]:
        assert save_score(client, name=name, score=score).status_code == 200
    data = client.get("/api/scores").json()["scores"]
    assert [s["score"] for s in data] == [50, 40, 30, 10]  # highest first
    assert data[1]["name"] == "Аноним"  # empty name defaults


def test_scores_limited_to_10(client, save_score):
    for i in range(15):
        save_score(client, name=f"P{i}", score=i)
    data = client.get("/api/scores").json()["scores"]
    assert len(data) == 10
    assert data[0]["score"] == 14  # only the top 10 survive


def test_name_trimmed(client, settings, save_score):
    save_score(client, name="Зина", score=5)
    rows = top_scores(get_conn(settings.db_path))
    assert rows[0]["name"] == "Зина"


def test_scores_empty_initially(client):
    assert client.get("/api/scores").json() == {"scores": []}


def test_score_stores_character(client, save_score):
    save_score(client, name="Kir", score=20, character=0)
    s = client.get("/api/scores").json()["scores"][0]
    assert s["character"] == 0
    assert s["time_ms"] > 0  # server-stamped elapsed, not client-supplied


def test_scores_filter_by_character(client, save_score):
    save_score(client, name="A", score=50, character=0)
    save_score(client, name="B", score=40, character=1)
    save_score(client, name="C", score=30, character=0)
    overall = client.get("/api/scores").json()["scores"]
    assert [s["name"] for s in overall] == ["A", "B", "C"]          # all, by score
    only0 = client.get("/api/scores?character=0").json()["scores"]
    assert [s["name"] for s in only0] == ["A", "C"]                 # character 0 only
    only1 = client.get("/api/scores?character=1").json()["scores"]
    assert [s["name"] for s in only1] == ["B"]


def test_scores_reject_bad_character_filter(client):
    assert client.get("/api/scores?character=9").status_code == 422


def test_scores_unique_per_name_max_score(client, save_score):
    # The same player (name) appearing many times keeps only their best run.
    save_score(client, name="sora", score=100, character=0)
    save_score(client, name="sora", score=300, character=1)
    save_score(client, name="sora", score=200, character=0)
    save_score(client, name="Феня", score=250, character=2)
    rows = client.get("/api/scores").json()["scores"]
    assert [(r["name"], r["score"]) for r in rows] == [("sora", 300), ("Феня", 250)]
    assert rows[0]["character"] == 1  # data of the best run

    # Per-character tab: unique per name WITHIN that character.
    only0 = client.get("/api/scores?character=0").json()["scores"]
    assert [(r["name"], r["score"]) for r in only0] == [("sora", 200)]
