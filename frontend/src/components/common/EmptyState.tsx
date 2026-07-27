import { IconInboxEmpty, type IconProps } from "@/components/icons";

interface Props {
  icon?: (props: IconProps) => JSX.Element;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ icon: Icon = IconInboxEmpty, title, description, action }: Props) {
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
