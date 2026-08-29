import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAnnouncement } from "@/api/announcement";
import { IconClose, IconParty } from "@/components/icons";
import { dismissAnnouncement, isAnnouncementDismissed } from "@/lib/announcementBanner";
import { useAuthStore } from "@/store/authStore";

export default function AnnouncementBanner() {
  const userId = useAuthStore((s) => s.user?.id);
  const { data } = useQuery({
    queryKey: ["announcement"],
    queryFn: fetchAnnouncement,
    refetchInterval: 30000,
    enabled: !!userId,
  });
  const [closed, setClosed] = useState(false);

  if (!userId || !data?.text || !data.updated_at || closed || isAnnouncementDismissed(userId, data.updated_at)) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 bg-accent-cyan/15 px-4 py-2 text-xs text-accent-cyan">
      <IconParty size={14} className="shrink-0" />
      <span className="flex-1 whitespace-pre-wrap">{data.text}</span>
      <button
        onClick={() => { dismissAnnouncement(userId, data.updated_at!); setClosed(true); }}
        aria-label="Закрыть"
        className="shrink-0"
      >
        <IconClose size={14} />
      </button>
    </div>
  );
}
