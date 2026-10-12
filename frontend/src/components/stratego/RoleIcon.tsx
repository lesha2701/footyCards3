import { IconBase, IconBoot, IconShirt, IconStar, IconTrophy, type IconProps } from "@/components/icons";
import type { StrategoRole } from "@/types";

/** Brick wall — "Стенка". Same 24px / 1.8 stroke alphabet as the app icon set. */
function IconWall(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <line x1="3" y1="9.7" x2="21" y2="9.7" />
      <line x1="3" y1="14.3" x2="21" y2="14.3" />
      <line x1="9" y1="5" x2="9" y2="9.7" />
      <line x1="15" y1="5" x2="15" y2="9.7" />
      <line x1="12" y1="9.7" x2="12" y2="14.3" />
      <line x1="9" y1="14.3" x2="9" y2="19" />
      <line x1="15" y1="14.3" x2="15" y2="19" />
    </IconBase>
  );
}

/** Theatre mask — "Провокатор". */
function IconMask(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 5.5c5.3 1.6 10.7 1.6 16 0v5.5a8 8 0 0 1-16 0Z" />
      <path d="M7.5 10.2c.8-.7 2-.7 2.8 0M13.7 10.2c.8-.7 2-.7 2.8 0" />
      <path d="M9 14.6c1.8 1.2 4.2 1.2 6 0" />
    </IconBase>
  );
}

/** Lightning bolt — "Скорость". */
function IconBolt(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M13.5 3 5.5 13.5h6L10.5 21l8-10.5h-6Z" />
    </IconBase>
  );
}

const ICONS: Record<StrategoRole, (props: IconProps) => JSX.Element> = {
  cup: IconTrophy,
  wall: IconWall,
  star: IconStar,
  tackler: IconBoot,
  provocateur: IconMask,
  speedster: IconBolt,
  regular: IconShirt,
};

export default function RoleIcon({ role, ...props }: IconProps & { role: StrategoRole }) {
  const Icon = ICONS[role];
  return <Icon {...props} />;
}
