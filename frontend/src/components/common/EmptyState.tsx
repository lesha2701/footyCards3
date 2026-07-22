interface Props {
  icon?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ icon = "📭", title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-white/5 bg-bg-surface px-6 py-12 text-center">
      <div className="text-4xl">{icon}</div>
      <p className="font-display text-lg text-slate-200">{title}</p>
      {description && <p className="max-w-xs text-sm text-slate-400">{description}</p>}
      {action}
    </div>
  );
}
