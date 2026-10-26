from services.newbie_reminder import gift_text


def test_day_two_names_the_coins():
    text = gift_text("Витя", 2, 10000, "legendary")
    assert "Витя" in text and "10 000 монет" in text and "второго дня" in text


def test_day_three_names_the_card_and_escapes_the_name():
    text = gift_text("<b>", 3, 10000, "legendary")
    assert "легендарная карта" in text and "&lt;b&gt;" in text
