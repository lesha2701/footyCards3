from services.daily_reminder import digest_text


def test_digest_lists_what_is_waiting():
    text = digest_text(True, 2)
    assert "ежедневная награда" in text and "выполненных заданий: 2" in text


def test_digest_only_tasks():
    assert "ежедневная" not in digest_text(False, 1)


def test_no_digest_when_nothing_is_waiting():
    assert digest_text(False, 0) is None
