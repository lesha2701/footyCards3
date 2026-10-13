"""Pure rules for «21: Добавленное время» — a simplified blackjack against the
bot «Тренер соперника». No DB access here; blackjack_service.py owns
persistence, limits and rewards (same split as stratego_engine/_service).

Deck: one 52-card deck, four "suits" = positions (gk/df/mf/fw), each with
2–10 at face value, three «Звёзды» (playmaker/striker/captain, worth 10)
and one «Легенда» (worth 1 or 11 — the ace). Cards are stored as compact
"suit:rank" strings in the match's server_state.

Rules (documented choices):
- Deal order: player, bot, player, bot (the bot's second card is the hidden
  "hole" card).
- Peek: if either side has a natural 21 with the first two cards the hand is
  over immediately — both natural → push; only the player → «Хет-трик»;
  only the bot → loss.
- Player actions are only hit («Ещё карту») and stand («Хватит»). No
  double/split/insurance. Reaching 21 auto-stands.
- Player over 21 → «Офсайд» (loss) and the bot doesn't draw.
- The bot draws while its total is below 17 and STANDS on every 17,
  including soft 17 (S17) — the friendlier, more common casino rule.
"""
import secrets

SUITS: tuple[str, ...] = ("gk", "df", "mf", "fw")
STAR_RANKS: tuple[str, ...] = ("playmaker", "striker", "captain")
LEGEND = "legend"
RANKS: tuple[str, ...] = tuple(str(n) for n in range(2, 11)) + STAR_RANKS + (LEGEND,)

DEALER_STANDS_ON = 17

OUTCOME_HAT_TRICK = "hat_trick"
OUTCOME_WIN = "win"
OUTCOME_PUSH = "push"
OUTCOME_LOSS = "loss"

_rng = secrets.SystemRandom()


def full_deck() -> list[str]:
    return [f"{suit}:{rank}" for suit in SUITS for rank in RANKS]


def shuffled_deck() -> list[str]:
    deck = full_deck()
    _rng.shuffle(deck)
    return deck


def card_rank(card: str) -> str:
    return card.split(":", 1)[1]


def card_value(card: str) -> int:
    """Hard value — a Legend counts 1 here; hand_value upgrades one to 11."""
    rank = card_rank(card)
    if rank == LEGEND:
        return 1
    if rank in STAR_RANKS:
        return 10
    return int(rank)


def hand_value(cards: list[str]) -> tuple[int, bool]:
    """(best total, is_soft). Soft = a Legend is currently counted as 11."""
    total = sum(card_value(c) for c in cards)
    has_legend = any(card_rank(c) == LEGEND for c in cards)
    if has_legend and total + 10 <= 21:
        return total + 10, True
    return total, False


def is_natural(cards: list[str]) -> bool:
    return len(cards) == 2 and hand_value(cards)[0] == 21


def is_bust(cards: list[str]) -> bool:
    return hand_value(cards)[0] > 21


def dealer_should_hit(cards: list[str]) -> bool:
    return hand_value(cards)[0] < DEALER_STANDS_ON


def deal(deck: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(player, dealer, remaining deck) — deck is consumed from the front."""
    deck = list(deck)
    player = [deck[0], deck[2]]
    dealer = [deck[1], deck[3]]
    return player, dealer, deck[4:]


def play_dealer(dealer: list[str], deck: list[str]) -> tuple[list[str], list[str]]:
    dealer, deck = list(dealer), list(deck)
    while dealer_should_hit(dealer):
        dealer.append(deck.pop(0))
    return dealer, deck


def initial_outcome(player: list[str], dealer: list[str]) -> tuple[str, str] | None:
    """Peek after the deal: (outcome, reason) if a natural ends the hand."""
    p_nat, d_nat = is_natural(player), is_natural(dealer)
    if p_nat and d_nat:
        return OUTCOME_PUSH, "both_natural"
    if p_nat:
        return OUTCOME_HAT_TRICK, "natural"
    if d_nat:
        return OUTCOME_LOSS, "dealer_natural"
    return None


def final_outcome(player: list[str], dealer: list[str]) -> tuple[str, str]:
    """Outcome once the player stood and the bot finished drawing."""
    if is_bust(player):
        return OUTCOME_LOSS, "offside"
    if is_bust(dealer):
        return OUTCOME_WIN, "dealer_offside"
    p, d = hand_value(player)[0], hand_value(dealer)[0]
    if p > d:
        return OUTCOME_WIN, "higher"
    if p < d:
        return OUTCOME_LOSS, "lower"
    return OUTCOME_PUSH, "equal"
