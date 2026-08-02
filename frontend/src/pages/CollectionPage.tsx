import { useState } from "react";

import AlbumTab from "@/components/collection/AlbumTab";
import MyCardsTab from "@/components/collection/MyCardsTab";

export default function CollectionPage() {
  const [tab, setTab] = useState<"album" | "mine">("album");

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Карточки</h1>

      <div className="grid grid-cols-2 gap-2 rounded-2xl bg-bg-surface p-1">
        <button
          onClick={() => setTab("album")}
          className={`rounded-xl py-2 text-sm font-semibold transition ${
            tab === "album" ? "bg-floodlight text-bg-base" : "text-ink-mist"
          }`}
        >
          Альбом
        </button>
        <button
          onClick={() => setTab("mine")}
          className={`rounded-xl py-2 text-sm font-semibold transition ${
            tab === "mine" ? "bg-floodlight text-bg-base" : "text-ink-mist"
          }`}
        >
          Мои карточки
        </button>
      </div>

      {tab === "album" ? <AlbumTab /> : <MyCardsTab />}
    </div>
  );
}
