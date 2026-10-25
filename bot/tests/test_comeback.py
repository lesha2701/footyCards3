from services.comeback import comeback_text


def test_text_names_the_player_and_what_waits():
    text = comeback_text("Лёша", True)
    assert text.startswith("👋 Лёша, давно не виделись!") and "бесплатный пак" in text


def test_text_without_a_name_or_a_ready_pack():
    text = comeback_text(None, False)
    assert text.startswith("👋 Давно не виделись!") and "бесплатный пак" not in text and "награда дня" in text


def test_name_is_escaped_for_html():
    assert "&lt;b&gt;" in comeback_text("<b>", False)
