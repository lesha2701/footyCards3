import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { CLUB_LOGO_COLORS, CLUB_LOGO_SHAPES, ClubLogo } from "@/components/clubs/ClubLogo";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import { createClub, fetchClubCreationCost } from "@/api/clubs";
import { ApiRequestError } from "@/lib/api";
import type { ClubLogoShape, ClubType } from "@/types";

export default function ClubCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [clubType, setClubType] = useState<ClubType>("open");
  const [shape, setShape] = useState<ClubLogoShape>("shield");
  const [color, setColor] = useState(CLUB_LOGO_COLORS[0]);
  const [error, setError] = useState<string | null>(null);
  const { data: creationCost } = useQuery({ queryKey: ["clubs", "creation-cost"], queryFn: fetchClubCreationCost });

  const mutation = useMutation({
    mutationFn: () => createClub({ name, description, club_type: clubType, logo_shape: shape, logo_color: color }),
    onSuccess: () => navigate("/clubs"),
    onError: (err) => setError(err instanceof ApiRequestError ? err.message : "Не удалось создать клуб"),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Новый клуб</h1>
      </div>

      <div className="flex justify-center">
        <ClubLogo shape={shape} color={color} size={80} />
      </div>

      <div className="flex flex-wrap justify-center gap-2">
        {CLUB_LOGO_SHAPES.map((s) => (
          <button
            key={s}
            onClick={() => setShape(s)}
            className={`rounded-xl p-2 ${shape === s ? "bg-bg-surface ring-2 ring-accent" : "bg-bg-surface"}`}
          >
            <ClubLogo shape={s} color={color} size={28} />
          </button>
        ))}
      </div>

      <div className="flex flex-wrap justify-center gap-2">
        {CLUB_LOGO_COLORS.map((c) => (
          <button
            key={c}
            onClick={() => setColor(c)}
            style={{ backgroundColor: c }}
            className={`h-8 w-8 rounded-full ${color === c ? "ring-2 ring-white" : ""}`}
          />
        ))}
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-ink-mist-dim">Название</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={64}
          className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-ink-mist-dim">Описание (необязательно)</span>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={512}
          rows={3}
          className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
        />
      </label>

      <div className="flex gap-2">
        <button
          onClick={() => setClubType("open")}
          className={`flex-1 rounded-xl py-2 text-xs font-semibold ${clubType === "open" ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
        >
          Открытый
        </button>
        <button
          onClick={() => setClubType("closed")}
          className={`flex-1 rounded-xl py-2 text-xs font-semibold ${clubType === "closed" ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
        >
          Закрытый (по заявке)
        </button>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {creationCost != null && (
        <p className="flex items-center justify-center gap-1.5 text-xs text-ink-mist-dim">
          Стоимость создания клуба:
          <span className="flex items-center gap-1 font-semibold text-ink-chalk">
            <IconCoin size={14} className="text-accent-cyan" />
            {creationCost}
          </span>
        </p>
      )}

      <button
        onClick={() => mutation.mutate()}
        disabled={name.trim().length < 3 || mutation.isPending}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {mutation.isPending ? "Создание..." : "Создать клуб"}
      </button>
    </div>
  );
}
