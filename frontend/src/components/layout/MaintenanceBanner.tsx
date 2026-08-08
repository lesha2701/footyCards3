import { useQuery } from "@tanstack/react-query";

import { fetchMaintenanceStatus } from "@/api/maintenance";
import { IconWarning } from "@/components/icons";

export default function MaintenanceBanner() {
  const { data } = useQuery({
    queryKey: ["maintenance-status"],
    queryFn: fetchMaintenanceStatus,
    refetchInterval: 30000,
  });

  if (!data?.active) return null;

  const minutesLeft = data.until ? Math.max(1, Math.ceil((new Date(data.until).getTime() - Date.now()) / 60000)) : null;

  return (
    <div className="flex items-center gap-2 bg-amber-500/15 px-4 py-2 text-xs text-amber-300">
      <IconWarning size={14} className="shrink-0" />
      <span>
        Идёт подготовка обновления — бот и приложение могут работать со сбоями
        {minutesLeft ? ` ещё ~${minutesLeft} мин` : " несколько минут"}.
      </span>
    </div>
  );
}
