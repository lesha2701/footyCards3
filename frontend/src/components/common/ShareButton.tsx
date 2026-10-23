import { useMutation } from "@tanstack/react-query";

import { prepareShare, type ShareKind } from "@/api/share";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify, shareToTelegram } from "@/lib/telegram";

/** «Поделиться в Telegram» for one of the player's own moments. The server
 * renders the image and checks ownership; this only asks for it and hands
 * the result to Telegram. */
export default function ShareButton({
  kind,
  id,
  label = "Поделиться",
  compact = false,
  className = "",
}: {
  kind: ShareKind;
  id: number;
  label?: string;
  compact?: boolean;
  className?: string;
}) {
  const share = useMutation({
    mutationFn: () => prepareShare(kind, id),
    onSuccess: async (prepared) => {
      haptic("light");
      const sent = await shareToTelegram(prepared.prepared_message_id, prepared.share_url);
      if (sent) hapticNotify("success");
    },
  });

  return (
    <div className={`flex flex-col items-center gap-1 ${className}`}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          share.mutate();
        }}
        disabled={share.isPending}
        className={`flex items-center justify-center gap-1.5 rounded-xl font-semibold active:scale-95 disabled:opacity-50 ${
          compact
            ? "w-full bg-white/10 px-2 py-1.5 text-caption text-ink-chalk"
            : "w-full bg-[#2AABEE] px-4 py-2.5 text-sm text-white"
        }`}
      >
        <TelegramPlane size={compact ? 12 : 16} />
        {share.isPending ? "Готовим…" : label}
      </button>
      {share.isError && (
        <p className="text-center text-caption text-red-400">{formatGameError(share.error, "Не удалось поделиться")}</p>
      )}
    </div>
  );
}

function TelegramPlane({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M21.9 4.3 18.7 19.4c-.2 1.1-.9 1.4-1.8.9l-4.9-3.6-2.4 2.3c-.3.3-.5.5-1 .5l.3-5 9.2-8.3c.4-.4-.1-.6-.6-.2L6.1 13.2 1.3 11.7c-1-.3-1.1-1 .2-1.5L20.6 2.8c.9-.3 1.6.2 1.3 1.5Z" />
    </svg>
  );
}
