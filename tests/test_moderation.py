from server.moderation import check_name


def _ok(name):
    return check_name(name)[0]


def test_valid_names_pass():
    for n in ["Alice", "Зина", "Bob_1", "cool-name", "Максим", "Хуан", "player42", ""]:
        assert _ok(n), n


def test_disallowed_characters_rejected():
    # spaces, punctuation, emoji, slash — everything but letters/digits/_/-
    for n in ["a b", "hi!", "no.dot", "x/y", "имя🙂", "quote'", "semi;colon", "at@sign"]:
        assert not _ok(n), n


def test_profanity_rejected():
    for n in ["хуй", "Пизда", "ебать", "блядь", "мудак", "пидор", "залупа"]:
        assert not _ok(n), n


def test_derivatives_rejected():
    # stems must catch derivatives, not just exact base words
    for n in ["zalupka", "залупка", "хуйло", "пиздец", "распиздяй", "ебанат",
              "долбоеб", "охуенно", "хуесос", "заебись", "пиздатый", "выебон"]:
        assert not _ok(n), n


def test_obscene_rejected():
    for n in ["сиськи", "письки", "penis", "sex", "порно", "вагина"]:
        assert not _ok(n), n


def test_war_terms_rejected():
    for n in ["война", "путин", "зеленский", "азов", "ukraina", "гитлер"]:
        assert not _ok(n), n


def test_war_slurs_rejected():
    for n in ["СВО", "сво", "ZOV", "zov", "зов", "зига", "кацап", "хохол",
              "хохлы", "хохлушка", "москаль", "ватник", "колорад", "рашка",
              "укроп", "kacap", "hohol"]:
        assert not _ok(n), n


def test_legit_names_not_falsely_flagged():
    # words that contain a swear-adjacent substring but are innocent
    for n in ["команда", "свобода", "свой", "рубля", "хлеб", "требовать",
              "хулиган", "Аманда", "Хуан", "зовите", "Кирилл", "Никита",
              "Саша", "Костя", "Максим"]:
        assert _ok(n), n


def test_evasion_rejected():
    # separators, repeats, homoglyphs, leetspeak, latin spelling
    for n in ["х_у_й", "хуууй", "xyй", "6лядь", "hui", "pizda", "blyad", "п-и-з-д-а"]:
        assert not _ok(n), n


def test_reason_messages():
    assert check_name("a b")[1] == "Только буквы, цифры, _ и -"
    assert check_name("хуй")[1] == "Недопустимое имя"


def test_endpoint_rejects_bad_name(client, save_score):
    r = save_score(client, name="хуй", score=10)
    assert r.status_code == 400
    assert r.json()["detail"] == "Недопустимое имя"
    # a name with a space is rejected for characters
    assert save_score(client, name="bad name", score=5).status_code == 400


def test_endpoint_accepts_clean_name(client, save_score):
    assert save_score(client, name="Кирилл_2026", score=7).status_code == 200
    # empty still allowed (defaults to Аноним upstream)
    assert save_score(client, name="", score=3).status_code == 200
