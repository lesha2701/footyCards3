import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  buyMyPlayerCosmetic,
  equipMyPlayerCosmetic,
  type MyPlayer,
  type MyPlayerCosmeticItem,
  type MyPlayerView,
} from "@/api/myPlayer";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

import PlayerAvatar from "./PlayerAvatar";

interface Props {
  view: MyPlayerView;
  player: MyPlayer;
  onSaved: (view: MyPlayerView) => void;
}

/** «Стиль»: accessories and card backgrounds for coins (prices from the
 * server config), equip/unequip what is owned. */
export default function MyPlayerStyleShop({ view, player, onSaved }: Props) {
  const [error, setError] = useState<string | null>(null);
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));
  const buy = useMutation({
    mutationFn: buyMyPlayerCosmetic,
    onSuccess: (next) => { hapticNotify("success"); setError(null); onSaved(next); },
    onError,
  });
  const equip = useMutation({
    mutationFn: ({ kind, code }: { kind: MyPlayerCosmeticItem["kind"]; code: string | null }) => equipMyPlayerCosmetic(kind, code),
    onSuccess: (next) => { setError(null); onSaved(next); },
    onError,
  });
  const busy = buy.isPending || equip.isPending;
  const groups: { kind: MyPlayerCosmeticItem["kind"]; title: string }[] = [
    { kind: "accessory", title: "Аксессуары" },
    { kind: "background", title: "Фон карточки" },
  ];

  return (
    <div className="flex flex-col gap-4">
      {groups.map(({ kind, title }) => {
        const items = view.cosmetics.catalog.filter((c) => c.kind === kind);
        if (!items.length) return null;
        const equipped = view.cosmetics[kind];
        return (
          <section key={kind} className="rounded-2xl bg-bg-surface p-4">
            <h2 className="font-display text-base font-bold text-ink-chalk">{title}</h2>
            <div className="mt-3 grid grid-cols-2 gap-3">
              {items.map((item) => {
                const isOn = equipped === item.code;
                return (
                  <div key={item.code} className={`overflow-hidden rounded-xl bg-bg-raised ${isOn ? "ring-2 ring-accent-lime" : ""}`}>
                    <PlayerAvatar
                      appearance={player.appearance}
                      accessory={kind === "accessory" ? item.code : player.accessory}
                      backdrop={kind === "background" ? item.code : player.background}
                      className="aspect-[5/6] w-full"
                    />
                    <div className="p-2">
                      <p className="truncate text-xs font-semibold text-ink-chalk">{item.name}</p>
                      {item.owned ? (
                        <button
                          disabled={busy}
                          onClick={() => equip.mutate({ kind, code: isOn ? null : item.code })}
                          className={`mt-1.5 w-full rounded-lg py-1.5 text-xs font-bold disabled:opacity-40 ${isOn ? "bg-bg-surface text-ink-mist" : "bg-floodlight text-bg-base"}`}
                        >
                          {isOn ? "Снять" : "Надеть"}
                        </button>
                      ) : (
                        <button
                          disabled={busy}
                          onClick={() => buy.mutate(item.code)}
                          className="mt-1.5 flex w-full items-center justify-center gap-1 rounded-lg bg-floodlight py-1.5 text-xs font-bold text-bg-base disabled:opacity-40"
                        >
                          <IconCoin size={12} /> {item.price}
                        </button>
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
