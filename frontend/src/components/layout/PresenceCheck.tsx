import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, ApiRequestError } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";

interface PresenceChallenge {
  token: string;
  options: number[];
  image_url: string;
}

interface PresenceAnswer {
  ok: boolean;
  challenge: PresenceChallenge | null;
  locked_until?: string;
}

async function fetchPresence(): Promise<PresenceChallenge | null> {
  const { data } = await api.get<PresenceChallenge | null>("/presence");
  return data;
}

/** «Ты здесь?»: after an hour of continuous play the server asks the player
 * to pick the number shown on a picture (backend presence_service). Until
 * then games don't pay or rate. The picture needs the auth headers, so it is
 * fetched as a blob instead of an <img src>. */
export default function PresenceCheck() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const { data: challenge } = useQuery({
    queryKey: ["presence"],
    queryFn: fetchPresence,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });

  const [imageUrl, setImageUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!challenge) {
      setImageUrl(null);
      return;
    }
    let revoked = false;
    let objectUrl: string | null = null;
    api.get(`/presence/image/${challenge.token}`, { responseType: "blob" }).then(({ data }) => {
      if (revoked) return;
      objectUrl = URL.createObjectURL(data as Blob);
      setImageUrl(objectUrl);
    });
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [challenge]);

  const answer = useMutation({
    mutationFn: async (value: number) =>
      (await api.post<PresenceAnswer>("/presence/answer", { token: challenge!.token, value })).data,
    onSuccess: (res) => {
      if (res.ok) {
        hapticNotify("success");
        setMessage(null);
      } else if (res.locked_until) {
        hapticNotify("error");
        const at = new Date(res.locked_until).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
        setMessage(`Слишком много ошибок. Награды за игры вернутся в ${at}.`);
      } else {
        hapticNotify("error");
        setMessage("Не то число — попробуй ещё раз.");
      }
      queryClient.setQueryData(["presence"], res.challenge);
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    },
    onError: (err) => setMessage(err instanceof ApiRequestError ? err.message : "Не получилось — попробуй ещё раз."),
  });

  if (!challenge) {
    return message ? (
      <div className="fixed inset-x-4 bottom-24 z-50 rounded-2xl bg-bg-surface p-3 text-center text-xs text-amber-200 shadow-lg" role="status">
        {message}
        <button onClick={() => setMessage(null)} className="ml-2 font-semibold text-accent-lime">OK</button>
      </div>
    ) : null;
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-sm rounded-3xl bg-bg-surface p-5 text-center">
        <p className="font-display text-lg font-bold text-ink-chalk">Ты здесь? 👋</p>
        <p className="mt-1 text-xs text-ink-mist">
          Ты играешь уже больше часа подряд. Нажми на число с картинки — и игры снова будут приносить монеты и рейтинг.
        </p>
        <div className="mx-auto mt-4 flex h-[120px] w-[240px] items-center justify-center overflow-hidden rounded-2xl bg-black/30">
          {imageUrl ? <img src={imageUrl} alt="Число для проверки" className="h-full w-full" /> : <span className="text-xs text-ink-mist-dim">…</span>}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          {challenge.options.map((value) => (
            <button
              key={value}
              disabled={answer.isPending}
              onClick={() => answer.mutate(value)}
              className="rounded-2xl bg-white/10 py-3 font-display text-xl font-bold text-ink-chalk active:scale-95 disabled:opacity-50"
            >
              {value}
            </button>
          ))}
        </div>
        {message && <p className="mt-3 text-xs text-red-400">{message}</p>}
      </div>
    </div>
  );
}
