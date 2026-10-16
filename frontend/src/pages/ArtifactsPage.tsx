import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";

import { fetchFriends } from "@/api/friends";
import { fetchArtifacts, giftArtifact, setArtifactActive } from "@/api/monetization";
import ArtifactShop from "@/components/artifacts/ArtifactShop";
import ArtifactTile from "@/components/artifacts/ArtifactTile";
import EmptyState from "@/components/common/EmptyState";
import { IconGift, IconTrophy } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import type { ArtifactCatalog, ArtifactCopy } from "@/types";

type Tab = "shelf" | "shop";

/** «Артефакты»: the active slots (only these give bonuses), the shelf
 * with every owned copy, and the shop. */
export default function ArtifactsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("shelf");
  const [selected, setSelected] = useState<ArtifactCopy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: catalog } = useQuery({ queryKey: ["artifacts"], queryFn: fetchArtifacts });

  const apply = (data: ArtifactCatalog) => {
    queryClient.setQueryData(["artifacts"], data);
    queryClient.invalidateQueries({ queryKey: ["my-player"] });
    setSelected(null);
    setError(null);
  };
  const toggle = useMutation({
    mutationFn: ({ copyId, active }: { copyId: number; active: boolean }) => setArtifactActive(copyId, active),
    onSuccess: (data) => {
      hapticNotify("success");
      apply(data);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось")),
  });
  const gift = useMutation({
    mutationFn: ({ copyId, friendId }: { copyId: number; friendId: number }) => giftArtifact(copyId, friendId),
    onSuccess: (data) => {
      hapticNotify("success");
      apply(data);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось подарить")),
  });

  if (!catalog) return null;
  const active = catalog.shelf.filter((c) => c.equipped);
  const shelf = catalog.shelf.filter((c) => !c.equipped);
  const effects = [
    ...catalog.effects.club.map((e) => ({ ...e, who: "Клуб" })),
    ...catalog.effects.my_player.map((e) => ({ ...e, who: "Мой игрок" })),
  ];

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTrophy size={20} className="text-amber-300" /> Артефакты
      </h1>
      <div className="grid grid-cols-2 gap-1 rounded-2xl bg-bg-surface p-1">
        {([["shelf", "Моя полка"], ["shop", "Магазин"]] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded-xl py-2 text-xs font-semibold ${tab === id ? "bg-accent-lime text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "shop" ? (
        <ArtifactShop />
      ) : !catalog.enabled ? (
        <EmptyState title="Артефакты скоро появятся" />
      ) : (
        <>
          <section className="rounded-2xl bg-bg-surface p-4">
            <p className="font-display text-sm font-bold text-ink-chalk">
              Активные · {catalog.active_count}/{catalog.slots}
            </p>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {Array.from({ length: catalog.slots }).map((_, i) => {
                const copy = active[i];
                return copy ? (
                  <button key={copy.copy_id} onClick={() => setSelected(copy)} className="flex flex-col items-center gap-1.5">
                    <ArtifactTile artifact={copy.artifact} serial={copy.serial_number} />
                    <span className="w-full truncate text-center text-caption text-ink-chalk">{copy.artifact.name}</span>
                  </button>
                ) : (
                  <span key={`empty-${i}`} className="flex aspect-square items-center justify-center rounded-2xl border border-dashed border-white/15 text-caption text-ink-mist-dim">
                    Пусто
                  </span>
                );
              })}
            </div>
            {effects.length > 0 ? (
              <ul className="mt-3 flex flex-col gap-1">
                {effects.map((e) => (
                  <li key={`${e.who}-${e.effect}`} className="text-xs text-accent-lime">
                    {e.who}: {e.label}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-xs text-ink-mist-dim">Поставь артефакты в слоты — бонусы дают только активные.</p>
            )}
          </section>

          <section className="rounded-2xl bg-bg-surface p-4">
            <p className="font-display text-sm font-bold text-ink-chalk">Полка</p>
            {shelf.length === 0 ? (
              <p className="mt-2 text-xs text-ink-mist-dim">
                {catalog.shelf.length ? "Все артефакты активны." : "Пока пусто — загляни в магазин."}
              </p>
            ) : (
              <div className="mt-3 grid grid-cols-3 gap-3">
                {shelf.map((copy) => (
                  <button key={copy.copy_id} onClick={() => setSelected(copy)} className="flex flex-col items-center gap-1.5">
                    <ArtifactTile artifact={copy.artifact} serial={copy.serial_number} dimmed size="sm" />
                    <span className="w-full truncate text-center text-micro text-ink-mist">{copy.artifact.name}</span>
                  </button>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {selected && (
        <CopySheet
          copy={selected}
          busy={toggle.isPending || gift.isPending}
          onToggle={() => toggle.mutate({ copyId: selected.copy_id, active: !selected.equipped })}
          onGift={(friendId) => gift.mutate({ copyId: selected.copy_id, friendId })}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function CopySheet({
  copy, busy, onToggle, onGift, onClose,
}: {
  copy: ArtifactCopy;
  busy: boolean;
  onToggle: () => void;
  onGift: (friendId: number) => void;
  onClose: () => void;
}) {
  const [picking, setPicking] = useState(false);
  const { data: friends } = useQuery({ queryKey: ["friends"], queryFn: fetchFriends, enabled: picking });
  const a = copy.artifact;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={onClose}>
      <motion.div
        initial={{ y: 40, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-bg-surface p-5 pb-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex gap-3">
          <ArtifactTile artifact={a} serial={copy.serial_number} />
          <div className="min-w-0">
            <p className="font-display text-lg font-bold text-ink-chalk">{a.name}</p>
            <p className="text-caption text-ink-mist">{a.target_label}{copy.source === "gift" ? " · подарок" : ""}</p>
            {a.active_label && <p className="mt-1 text-xs text-accent-lime">{a.active_label}</p>}
            {a.card_label && <p className="text-xs text-accent-lime">{a.card_label}</p>}
            {a.description && <p className="mt-1 text-caption text-ink-mist-dim">{a.description}</p>}
          </div>
        </div>
        {!picking ? (
          <div className="mt-4 flex flex-col gap-2">
            <button
              onClick={onToggle}
              disabled={busy}
              className={`rounded-2xl py-3 text-sm font-bold disabled:opacity-40 ${
                copy.equipped ? "bg-white/10 text-ink-chalk" : "bg-floodlight text-bg-base"
              }`}
            >
              {copy.equipped ? "Убрать на полку" : "Сделать активным"}
            </button>
            <button
              onClick={() => setPicking(true)}
              disabled={busy}
              className="flex items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist disabled:opacity-40"
            >
              <IconGift size={15} /> Подарить другу
            </button>
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-1.5">
            <p className="text-xs text-ink-mist">Кому подарить №{copy.serial_number}?</p>
            {friends?.friends.length === 0 && <p className="text-xs text-ink-mist-dim">Пока нет друзей — добавь их в профиле.</p>}
            {friends?.friends.map((f) => (
              <button
                key={f.user.id}
                onClick={() => onGift(f.user.id)}
                disabled={busy}
                className="rounded-xl bg-white/5 px-3 py-2.5 text-left text-sm text-ink-chalk disabled:opacity-40"
              >
                {f.user.first_name ?? f.user.username ?? `Игрок #${f.user.id}`}
              </button>
            ))}
            <button onClick={() => setPicking(false)} className="mt-1 text-xs text-ink-mist">Назад</button>
          </div>
        )}
      </motion.div>
    </div>
  );
}
