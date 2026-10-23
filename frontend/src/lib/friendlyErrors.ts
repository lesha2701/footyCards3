/** Player-facing error text. The backend still answers some actions in
 * English and network failures arrive as axios' "Request failed with status
 * code 500"; players should never see either. Russian server messages pass
 * through unchanged. */

const KNOWN: Record<string, string> = {
  "Not enough coins": "Не хватает монет",
  "Card not found": "Карточка не найдена — возможно, её уже нет в коллекции",
  "One or more cards not found": "Некоторых карточек уже нет в коллекции",
  "Match not found": "Матч не найден",
  "Game session not found": "Игра не найдена — начни новую",
  "This game session has already finished": "Эта игра уже закончилась",
  "This game session is not in progress": "Эта игра уже закончилась",
  "Session is still in progress": "Сначала доиграй текущую игру",
  "Reward for this session has already been claimed": "Награда за эту игру уже получена",
  "This session does not belong to you": "Это не твоя игра",
  "You are not part of this match": "Ты не участвуешь в этом матче",
  "This match does not belong to you": "Это не твой матч",
  "This match is not in progress": "Этот матч уже завершён",
  "This draft has already finished": "Этот драфт уже закончился",
  "This challenge is no longer pending": "Этот вызов уже неактуален",
  "This challenge is no longer available": "Этот вызов уже неактуален",
  "This challenge has expired": "Время на вызов истекло",
  "You cannot challenge yourself": "Нельзя вызвать самого себя",
  "You cannot accept your own challenge": "Нельзя принять свой же вызов",
  "This user is banned and cannot be challenged": "Этого игрока нельзя вызвать",
  "User not found": "Игрок не найден",
  "Player not found": "Футболист не найден",
  "Pack not found": "Пак не найден",
  "This pack is not currently available": "Этот пак сейчас недоступен",
  "Trade offer not found": "Обмен не найден",
  "This offer is no longer pending": "Этот обмен уже неактуален",
  "You can only use your own cards": "Можно использовать только свои карточки",
  "This card does not belong to you": "Это не твоя карточка",
  "This card is locked and cannot be upgraded": "Карточка заблокирована — сейчас её нельзя улучшить",
  "Card is used in an active lineup": "Карточка стоит в составе — сначала замени её",
  "Card is used in your Tactico squad": "Карточка стоит в составе Тактико — сначала замени её",
  "Card is locked in an active trade": "Карточка участвует в обмене",
  "Card is locked by an administrator": "Карточка заблокирована администратором",
  "Trophy not found": "Трофей не найден",
  "Invoice not found": "Счёт не найден — попробуй купить ещё раз",
  "Gift set not found": "Подарок не найден",
};

const BY_STATUS: Record<number, string> = {
  400: "Не получилось — проверь данные и попробуй ещё раз",
  401: "Сессия устарела — закрой и снова открой приложение",
  403: "Это действие тебе недоступно",
  404: "Не нашли то, что ты ищешь — обнови экран",
  409: "Сейчас это сделать нельзя — обнови экран и попробуй ещё раз",
  422: "Не получилось — проверь данные и попробуй ещё раз",
  429: "Слишком часто — подожди немного и попробуй снова",
};

const SERVER_DOWN = "Сервер на секунду задумался — попробуй ещё раз";
const OFFLINE = "Нет связи с сервером — проверь интернет и попробуй ещё раз";

const hasCyrillic = (s: string) => /[а-яё]/i.test(s);

/** `message` from the server (or axios), the HTTP status if there was a
 * response at all. Returns Russian text fit for a player. */
export function friendlyMessage(message: string | undefined, status: number | undefined, fromServer: boolean): string {
  const text = (message ?? "").trim();
  if (fromServer && text) {
    if (hasCyrillic(text)) return text;
    if (KNOWN[text]) return KNOWN[text];
    if (text.startsWith("Telegram auth failed")) return BY_STATUS[401];
  }
  if (status === undefined) return OFFLINE;
  if (status >= 500) return SERVER_DOWN;
  return BY_STATUS[status] ?? SERVER_DOWN;
}
