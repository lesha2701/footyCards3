import { IconInboxEmpty, type IconProps } from "@/components/icons";

interface Props {
  icon?: (props: IconProps) => JSX.Element;
  title: string;
  description?: string;
  action?: React.ReactNode;
  /** Inside a card or a sheet: smaller, on an inset background. */
  compact?: boolean;
}

export default function EmptyState({ icon: Icon = IconInboxEmpty, title, description, action, compact = false }: Props) {
  if (compact) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-2xl bg-bg-base/40 px-4 py-5 text-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-bg-raised text-ink-mist">
          <Icon size={20} />
        </div>
        <p className="font-display text-sm font-bold text-ink-chalk">{title}</p>
        {description && <p className="max-w-xs text-caption text-ink-mist">{description}</p>}
        {action}
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl bg-bg-surface px-6 py-12 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-bg-raised text-ink-mist">
        <Icon size={26} />
      </div>
      <p className="font-display text-base font-bold text-ink-chalk">{title}</p>
      {description && <p className="max-w-xs text-sm text-ink-mist">{description}</p>}
      {action}
    </div>
  );
}
