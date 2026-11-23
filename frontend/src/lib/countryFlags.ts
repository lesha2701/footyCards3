import { staticUrl } from "@/lib/api";

/** A player's country (stored as its Russian name, sometimes English) →
 * its flag, for the legendary «выход». The flags are SVGs in
 * static/flags (flag-icons, MIT) rather than emoji: Windows and Telegram
 * Desktop draw a flag emoji as two letters. Unknown → null, and the
 * caller shows a globe instead. */
const CODES: Record<string, string> = {
  "Англия": "gb-eng", "Шотландия": "gb-sct", "Уэльс": "gb-wls", "Северная Ирландия": "gb-nir", "Великобритания": "gb",
  "Ирландия": "ie", "Франция": "fr", "Германия": "de", "Испания": "es", "Италия": "it", "Португалия": "pt",
  "Нидерланды": "nl", "Голландия": "nl", "Бельгия": "be", "Швейцария": "ch", "Австрия": "at",
  "Дания": "dk", "Швеция": "se", "Норвегия": "no", "Финляндия": "fi", "Исландия": "is",
  "Польша": "pl", "Чехия": "cz", "Словакия": "sk", "Венгрия": "hu", "Румыния": "ro", "Болгария": "bg",
  "Сербия": "rs", "Хорватия": "hr", "Босния и Герцеговина": "ba", "Словения": "si", "Черногория": "me",
  "Северная Македония": "mk", "Македония": "mk", "Албания": "al", "Косово": "xk", "Греция": "gr", "Турция": "tr",
  "Кипр": "cy", "Россия": "ru", "Украина": "ua", "Беларусь": "by", "Белоруссия": "by", "Молдова": "md",
  "Грузия": "ge", "Армения": "am", "Азербайджан": "az", "Казахстан": "kz", "Узбекистан": "uz",
  "Таджикистан": "tj", "Киргизия": "kg", "Кыргызстан": "kg", "Туркменистан": "tm",
  "Литва": "lt", "Латвия": "lv", "Эстония": "ee", "Израиль": "il", "Люксембург": "lu",
  "Бразилия": "br", "Аргентина": "ar", "Уругвай": "uy", "Колумбия": "co", "Чили": "cl", "Перу": "pe",
  "Эквадор": "ec", "Парагвай": "py", "Венесуэла": "ve", "Боливия": "bo", "Мексика": "mx", "США": "us",
  "Канада": "ca", "Коста-Рика": "cr", "Ямайка": "jm", "Панама": "pa", "Гондурас": "hn",
  "Сенегал": "sn", "Нигерия": "ng", "Гана": "gh", "Кот-д'Ивуар": "ci", "Кот-д’Ивуар": "ci", "Камерун": "cm",
  "Египет": "eg", "Марокко": "ma", "Алжир": "dz", "Тунис": "tn", "Мали": "ml", "Гвинея": "gn", "ДР Конго": "cd",
  "Буркина-Фасо": "bf", "ЮАР": "za", "Габон": "ga", "Либерия": "lr", "Того": "tg", "Ангола": "ao",
  "Япония": "jp", "Южная Корея": "kr", "Корея": "kr", "Китай": "cn", "Австралия": "au", "Иран": "ir",
  "Саудовская Аравия": "sa", "Катар": "qa", "ОАЭ": "ae", "Новая Зеландия": "nz",
  "England": "gb-eng", "France": "fr", "Germany": "de", "Spain": "es", "Italy": "it", "Portugal": "pt",
  "Netherlands": "nl", "Belgium": "be", "Brazil": "br", "Argentina": "ar", "Croatia": "hr",
  "Ukraine": "ua", "Russia": "ru", "Poland": "pl", "Uruguay": "uy", "Norway": "no", "Egypt": "eg",
};

const NORMALISED: Record<string, string> = Object.fromEntries(
  Object.entries(CODES).map(([name, code]) => [name.toLowerCase().replace(/ё/g, "е"), code]),
);

/** ISO code of the flag file, e.g. "br" or "gb-eng". */
export function countryCode(country: string | null | undefined): string | null {
  if (!country) return null;
  return NORMALISED[country.trim().toLowerCase().replace(/ё/g, "е")] ?? null;
}

export const ALL_FLAG_CODES: string[] = [...new Set(Object.values(CODES))];

export function countryFlagUrl(country: string | null | undefined): string | null {
  const code = countryCode(country);
  return code ? (staticUrl(`flags/${code}.svg`) ?? null) : null;
}
