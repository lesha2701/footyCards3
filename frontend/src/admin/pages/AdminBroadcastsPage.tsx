import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { sendUpdateBroadcast } from "@/admin/api";
import { ApiRequestError } from "@/lib/api";
import { showConfirm } from "@/lib/telegram";

export default function AdminBroadcastsPage() {
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<number | null>(null);

  const sendMutation = useMutation({
    mutationFn: () => sendUpdateBroadcast(message.trim()),
    onSuccess: (res) => { setResult(res.recipients); setError(null); setMessage(""); },
    onError: (err) => { setError(err instanceof ApiRequestError ? err.message : "Не удалось отправить рассылку"); setResult(null); },
  });

  const send = async () => {
    if (!message.trim()) return;
    if (!(await showConfirm("Отправить это сообщение всем пользователям бота? Отменить рассылку будет нельзя."))) return;
    setResult(null);
    sendMutation.mutate();
  };

  return (
    <div className="flex max-w-lg flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Рассылка об обновлении</h1>
      <p className="text-xs text-slate-400">
        Сообщение уйдёт в Telegram всем незабаненным пользователям бота. Одновременно в мини-аппе у всех появится
        баннер «Вышло обновление! Рекомендуем обновить страницу» — он не зависит от текста ниже и закрывается
        пользователем самостоятельно.
      </p>

      <textarea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={6}
        maxLength={1024}
        placeholder="Текст сообщения для бота, например: «Вышло обновление 2.4 — новые паки и исправления багов!»"
        className="rounded-lg bg-bg-surface px-3 py-2 text-sm outline-none"
      />

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {result !== null && (
        <p className="rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">Отправлено {result} пользователям.</p>
      )}

      <button
        onClick={send}
        disabled={!message.trim() || sendMutation.isPending}
        className="self-start rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-bg-base disabled:opacity-40"
      >
        {sendMutation.isPending ? "Отправка..." : "Отправить всем"}
      </button>
    </div>
  );
}
