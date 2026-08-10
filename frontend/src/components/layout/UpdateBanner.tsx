import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchUpdateStatus } from "@/api/updates";
import { IconClose } from "@/components/icons";
import { dismissUpdate, isUpdateDismissed } from "@/lib/updateBanner";
import { useAuthStore } from "@/store/authStore";

export default function UpdateBanner() {
  const userId = useAuthStore((s) => s.user?.id);
  const { data } = useQuery({
    queryKey: ["update-status"],
    queryFn: fetchUpdateStatus,
    refetchInterval: 30000,
    enabled: !!userId,
  });
  const [closed, setClosed] = useState(false);

  if (!userId || !data?.broadcast_at || closed || isUpdateDismissed(userId, data.broadcast_at)) return null;

  return (
    <div className="flex items-center gap-2 bg-accent/15 px-4 py-2 text-xs text-accent">
      <span className="flex-1">Вышло обновление! Рекомендуем обновить страницу.</span>
      <button
        onClick={() => { dismissUpdate(userId, data.broadcast_at!); setClosed(true); }}
        aria-label="Закрыть"
        className="shrink-0"
      >
        <IconClose size={14} />
      </button>
    </div>
  );
}
