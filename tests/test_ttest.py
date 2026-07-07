from server.metrics import welch_t_test, _betai


def test_incomplete_beta_uniform_and_bounds():
    assert abs(_betai(1, 1, 0.3) - 0.3) < 1e-9   # I_x(1,1) == x
    assert _betai(2, 3, 0.0) == 0.0
    assert _betai(2, 3, 1.0) == 1.0


def test_t_pvalue_matches_table():
    # Known two-sided p for t=2, df=8 is ~0.0805 (Student's t table).
    p = _betai(8 / 2, 0.5, 8 / (8 + 2 * 2))
    assert abs(p - 0.0805) < 0.002


def test_identical_groups_not_significant():
    r = welch_t_test(100, 50, 100, 50)
    assert r is not None
    assert abs(r["t"]) < 1e-9 and r["p"] > 0.99


def test_clear_difference_is_significant():
    r = welch_t_test(200, 100, 200, 40)   # 50% vs 20%
    assert r is not None and r["p"] < 0.001


def test_symmetric_in_arguments():
    a = welch_t_test(120, 60, 80, 20)
    b = welch_t_test(80, 20, 120, 60)
    assert abs(a["p"] - b["p"]) < 1e-9


def test_too_few_sessions_returns_none():
    assert welch_t_test(1, 0, 100, 50) is None
    assert welch_t_test(100, 50, 0, 0) is None


def test_no_variance_returns_none():
    # both groups all-zero conversions -> no variance -> undefined
    assert welch_t_test(50, 0, 50, 0) is None
