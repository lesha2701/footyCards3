import { useNavigate } from "react-router-dom";

import { useMatchGuardStore } from "@/store/matchGuardStore";

export default function LeaveConfirmDialog() {
  const navigate = useNavigate();
  const pendingTo = useMatchGuardStore((s) => s.pendingTo);
  const message = useMatchGuardStore((s) => s.message);
  const onLeave = useMatchGuardStore((s) => s.onLeave);
  const cancelNavigate = useMatchGuardStore((s) => s.cancelNavigate);
  const deactivate = useMatchGuardStore((s) => s.deactivate);

  if (!pendingTo) return null;

  const confirm = () => {
    onLeave?.();
    const to = pendingTo;
    deactivate();
    navigate(to);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-6" onClick={cancelNavigate}>
      <div className="w-full max-w-sm rounded-2xl bg-bg-surface p-5 text-center" onClick={(e) => e.stopPropagation()}>
        <p className="font-display text-base font-bold text-ink-chalk">Покинуть матч?</p>
        <p className="mt-2 text-sm text-ink-mist">{message}</p>
        <div className="mt-4 flex gap-2">
          <button
            onClick={cancelNavigate}
            className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-chalk active:scale-95"
          >
            Остаться
          </button>
          <button onClick={confirm} className="flex-1 rounded-xl bg-red-500/80 py-2.5 text-sm font-bold text-white active:scale-95">
            Выйти
          </button>
        </div>
      </div>
    </div>
  );
}
