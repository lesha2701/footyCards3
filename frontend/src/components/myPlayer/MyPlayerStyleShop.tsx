import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  buyMyPlayerCosmetic,
  equipMyPlayerCosmetic,
  type MyPlayer,
  type MyPlayerCosmeticItem,
  type MyPlayerCosmeticKind,
  type MyPlayerView,
} from "@/api/myPlayer";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { COSMETIC_GROUPS } from "@/lib/myPlayer";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { haptic, hapticNotify } from "@/lib/telegram";

import CardEffect from "./CardEffect";
import PlayerAvatar from "./PlayerAvatar";

export type StylePreview = Partial<Record<MyPlayerCosmeticKind, string | null>>;

interface Props {
  view: MyPlayerView;
  player: MyPlayer;
  preview: StylePreview;
  /** Try an item on: the hero card above shows it before buying. */
  onPreview: (preview: StylePreview) => void;
  onSaved: (view: MyPlayerView) => void;
}

/** «Раздевалка»: accessories, card backgrounds and card effects for coins
 * and/or Telegram Stars (prices from the server config). Tapping an item
 * tries it on the big card; owned items are put on / taken off. */
export default function MyPlayerStyleShop({ view, player, preview, onPreview, onSaved }: Props) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [starsBusy, setStarsBusy] = useState<string | null>(null);
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));
  const done = (next: MyPlayerView) => { setError(null); onPreview({}); onSaved(next); };
  const buy = useMutation({
    mutationFn: buyMyPlayerCosmetic,
    onSuccess: (next) => { hapticNotify("success"); done(next); },
    onError,
  });
  const equip = useMutation({
    mutationFn: ({ kind, code }: { kind: MyPlayerCosmeticKind; code: string | null }) => equipMyPlayerCosmetic(kind, code),
    onSuccess: done,
    onError,
  });
  const buyStars = async (item: MyPlayerCosmeticItem) => {
    setError(null);
    setStarsBusy(item.code);
    try {
      if ((await payMyPlayerWithStars({ purchase: "cosmetic", code: item.code })) === "paid") {
        hapticNotify("success");
        onPreview({});
        await queryClient.invalidateQueries({ queryKey: ["my-player"] });
      }
    } catch (err) {
      onError(err);
    } finally {
      setStarsBusy(null);
    }
  };
  const busy = buy.isPending || equip.isPending || starsBusy !== null;
  const trying = Object.keys(preview).length > 0;

  return (
    <div className="flex flex-col gap-4">
      <p className="-mb-1 text-center text-caption text-ink-mist">
        {trying ? "Примерка на карточке выше" : "Нажми на вещь — примеришь её на карточке"}
        {trying && (
          <button onClick={() => onPreview({})} className="ml-2 font-semibold text-accent-lime">Сбросить</button>
        )}
      </p>
      {COSMETIC_GROUPS.map(({ kind, title }) => {
        const items = view.cosmetics.catalog.filter((c) => c.kind === kind);
        if (!items.length) return null;
        const equipped = view.cosmetics[kind];
        return (
          <section key={kind} className="rounded-2xl bg-bg-surface p-4">
            <h2 className="font-display text-base font-bold text-ink-chalk">{title}</h2>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {items.map((item) => {
                const isOn = equipped === item.code;
                const isTried = preview[kind] === item.code;
                return (
                  <div
                    key={item.code}
                    className={`flex flex-col overflow-hidden rounded-xl bg-bg-raised ${
                      isTried ? "ring-2 ring-accent-cyan" : isOn ? "ring-2 ring-accent-lime" : ""
                    }`}
                  >
                    <button
                      aria-label={`Примерить: ${item.name}`}
                      onClick={() => {
                        haptic("light");
                        const next = { ...preview };
                        if (isTried) delete next[kind];
                        else next[kind] = item.code;
                        onPreview(next);
                      }}
                      className="relative aspect-[5/6] w-full overflow-hidden"
                    >
                      <PlayerAvatar
                        appearance={player.appearance}
                        accessory={kind === "accessory" ? item.code : player.accessory}
                        backdrop={kind === "background" ? item.code : player.background}
                        className="h-full w-full"
                      />
                      {kind === "effect" && <CardEffect effect={item.code} />}
                      {item.stars_price > 0 && !item.owned && (
                        <span className="absolute right-1 top-1 rounded-full bg-amber-400 px-1.5 text-micro font-bold text-bg-base">⭐</span>
                      )}
                    </button>
                    <div className="flex flex-1 flex-col p-1.5">
                      <p className="line-clamp-2 min-h-[2rem] text-micro font-semibold leading-tight text-ink-chalk">{item.name}</p>
                      {item.owned ? (
                        <button
                          disabled={busy}
                          onClick={() => equip.mutate({ kind, code: isOn ? null : item.code })}
                          className={`mt-1 w-full rounded-lg py-1.5 text-micro font-bold disabled:opacity-40 ${isOn ? "bg-bg-surface text-ink-mist" : "bg-floodlight text-bg-base"}`}
                        >
                          {isOn ? "Снять" : "Надеть"}
                        </button>
                      ) : (
                        <div className="mt-1 flex flex-col gap-1">
                          {item.price > 0 && (
                            <button
                              disabled={busy}
                              onClick={() => buy.mutate(item.code)}
                              className="flex w-full items-center justify-center gap-1 rounded-lg bg-floodlight py-1.5 text-micro font-bold text-bg-base disabled:opacity-40"
                            >
                              <IconCoin size={11} /> {item.price}
                            </button>
                          )}
                          {item.stars_price > 0 && (
                            <button
                              disabled={busy}
                              onClick={() => buyStars(item)}
                              className="w-full rounded-lg bg-amber-400 py-1.5 text-micro font-bold text-bg-base disabled:opacity-40"
                            >
                              ⭐ {item.stars_price}
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
    </div>
  );
}
