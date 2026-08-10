import { useEffect } from "react";

import { useAdminToastStore } from "@/admin/adminToastStore";
import { IconCheck, IconClose, IconWarning } from "@/components/icons";

const AUTO_DISMISS_MS = 3000;

export default function AdminToastContainer() {
  const toasts = useAdminToastStore((s) => s.toasts);
  const dismiss = useAdminToastStore((s) => s.dismiss);

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
      {toasts.map((t) => (
        <ToastItem key={t.id} id={t.id} message={t.message} kind={t.kind} onDismiss={dismiss} />
      ))}
    </div>
  );
}

function ToastItem({ id, message, kind, onDismiss }: { id: number; message: string; kind: "success" | "error"; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [id, onDismiss]);

  const isSuccess = kind === "success";
  return (
    <div
      className={`pointer-events-auto flex items-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-semibold shadow-lg ${
        isSuccess ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300" : "border-red-500/30 bg-red-500/15 text-red-300"
      }`}
    >
      {isSuccess ? <IconCheck size={14} className="shrink-0" /> : <IconWarning size={14} className="shrink-0" />}
      <span>{message}</span>
      <button onClick={() => onDismiss(id)} aria-label="Закрыть" className="ml-1 shrink-0 opacity-70">
        <IconClose size={12} />
      </button>
    </div>
  );
}
