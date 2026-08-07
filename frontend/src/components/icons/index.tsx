import { IconBase, type IconProps } from "./Icon";

export { IconBase };
export type { IconProps };

export function IconHome(props: IconProps) {
  return (
    <IconBase {...props}>
      <polyline points="4,11 12,4 20,11" />
      <rect x="6" y="11" width="12" height="9" rx="2" />
      <rect x="10" y="15" width="4" height="5" rx="1.3" />
    </IconBase>
  );
}

export function IconCoin(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.6" />
    </IconBase>
  );
}

export function IconPack(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="4" y="9" width="16" height="11" rx="2" />
      <rect x="3" y="6" width="18" height="4" rx="1.5" />
      <line x1="12" y1="6" x2="12" y2="20" />
    </IconBase>
  );
}

export function IconGift(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="4" y="10" width="16" height="10" rx="2" />
      <line x1="12" y1="10" x2="12" y2="20" />
      <line x1="4" y1="14" x2="20" y2="14" />
      <circle cx="9" cy="6" r="2.1" />
      <circle cx="15" cy="6" r="2.1" />
      <line x1="12" y1="8" x2="12" y2="10" />
    </IconBase>
  );
}

export function IconCollection(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="7" y="3" width="12" height="16" rx="2.5" />
      <rect x="4" y="6" width="12" height="16" rx="2.5" fill="var(--icon-mask, #07090a)" />
    </IconBase>
  );
}

export function IconPlay(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8" />
      <polygon points="10,8.5 16,12 10,15.5" fill="currentColor" stroke="none" />
    </IconBase>
  );
}

export function IconSwap(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="4" y1="8" x2="16" y2="8" />
      <polyline points="13,5 16,8 13,11" />
      <line x1="20" y1="16" x2="8" y2="16" />
      <polyline points="11,13 8,16 11,19" />
    </IconBase>
  );
}

export function IconProfile(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="8" r="4" />
      <rect x="5" y="15" width="14" height="7" rx="6" />
    </IconBase>
  );
}

export function IconTrophy(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="8" y="4" width="8" height="8" rx="2" />
      <circle cx="5" cy="7" r="2" />
      <circle cx="19" cy="7" r="2" />
      <line x1="8" y1="6" x2="6.5" y2="7" />
      <line x1="16" y1="6" x2="17.5" y2="7" />
      <line x1="12" y1="12" x2="12" y2="16" />
      <rect x="8" y="18" width="8" height="2" rx="1" />
    </IconBase>
  );
}

export function IconTarget(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="7" />
      <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
      <line x1="12" y1="1" x2="12" y2="4" />
      <line x1="12" y1="20" x2="12" y2="23" />
      <line x1="1" y1="12" x2="4" y2="12" />
      <line x1="20" y1="12" x2="23" y2="12" />
    </IconBase>
  );
}

export function IconBall(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8" />
      <polygon points="12,8.6 15,10.8 13.8,14.4 10.2,14.4 9,10.8" />
      <line x1="12" y1="4" x2="12" y2="8.6" />
      <line x1="15" y1="10.8" x2="18.8" y2="9.6" />
      <line x1="13.8" y1="14.4" x2="15.6" y2="18.4" />
      <line x1="10.2" y1="14.4" x2="8.4" y2="18.4" />
      <line x1="9" y1="10.8" x2="5.2" y2="9.6" />
    </IconBase>
  );
}

export function IconHelp(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8" />
      <path d="M9.6 9.5a2.4 2.4 0 1 1 3.4 2.2c-0.9 0.5-1 1-1 1.8" />
      <circle cx="12" cy="16.3" r="0.15" fill="currentColor" stroke="currentColor" strokeWidth="1.6" />
    </IconBase>
  );
}

export function IconChevronRight(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="13,6 19,12 13,18" />
    </IconBase>
  );
}

export function IconChevronLeft(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="11,6 5,12 11,18" />
    </IconBase>
  );
}

export function IconChevronUp(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="6,11 12,5 18,11" />
    </IconBase>
  );
}

export function IconClose(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </IconBase>
  );
}

export function IconCheck(props: IconProps) {
  return (
    <IconBase {...props}>
      <polyline points="5,13 10,18 19,7" />
    </IconBase>
  );
}

export function IconBan(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8" />
      <line x1="6.3" y1="6.3" x2="17.7" y2="17.7" />
    </IconBase>
  );
}

export function IconFire(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.5c1.2 2.3 3.6 3.6 3.6 6.8a3.6 3.6 0 1 1-7.2 0c0-1 .3-1.8.8-2.5.2 1 1 1.4 1.3.8-.5-2 .3-3.5 1.5-5.1Z" />
    </IconBase>
  );
}

export function IconLock(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="5" y="11" width="14" height="9" rx="2.5" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      <circle cx="12" cy="15.2" r="1.1" fill="currentColor" stroke="none" />
    </IconBase>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <line x1="15.3" y1="15.3" x2="20" y2="20" />
    </IconBase>
  );
}

export function IconTrash(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="5" y1="7" x2="19" y2="7" />
      <path d="M8 7V5.5A1.5 1.5 0 0 1 9.5 4h5A1.5 1.5 0 0 1 16 5.5V7" />
      <path d="M7 7l1 12.5A1.5 1.5 0 0 0 9.5 21h5a1.5 1.5 0 0 0 1.5-1.5L17 7" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </IconBase>
  );
}

export function IconChart(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="4" y1="20" x2="20" y2="20" />
      <rect x="6" y="13" width="3.4" height="7" rx="1" />
      <rect x="10.3" y="8" width="3.4" height="12" rx="1" />
      <rect x="14.6" y="4.5" width="3.4" height="15.5" rx="1" />
    </IconBase>
  );
}

export function IconWarning(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 4.5 21 19H3Z" strokeLinejoin="round" />
      <line x1="12" y1="10" x2="12" y2="14.2" />
      <circle cx="12" cy="16.7" r="0.15" fill="currentColor" stroke="currentColor" strokeWidth="1.6" />
    </IconBase>
  );
}

export function IconMenu(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="4" y1="7" x2="20" y2="7" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="17" x2="20" y2="17" />
    </IconBase>
  );
}

export function IconEdit(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M6 18.5 6.6 15.4 15.7 6.3a1.6 1.6 0 0 1 2.3 0l0 0a1.6 1.6 0 0 1 0 2.3L9 17.7 6 18.5Z" strokeLinejoin="round" />
    </IconBase>
  );
}

export function IconPlus(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </IconBase>
  );
}

export function IconGlobe(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8" />
      <ellipse cx="12" cy="12" rx="3.4" ry="8" />
      <line x1="4" y1="12" x2="20" y2="12" />
    </IconBase>
  );
}

export function IconParty(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M5 19 15 6l3 3L5 19Z" strokeLinejoin="round" />
      <line x1="15" y1="4" x2="15" y2="6.3" />
      <line x1="19.7" y1="8.5" x2="17.4" y2="8.5" />
      <line x1="17.7" y1="5" x2="19.2" y2="6.5" />
    </IconBase>
  );
}

export function IconHandshake(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M3 12l4-3.4a2 2 0 0 1 2.5 0L12 11l2.5-2.4a2 2 0 0 1 2.5 0L21 12" />
      <path d="M7 11.5 10.5 15a1.6 1.6 0 0 0 2.3 0l0.2-.2a1.6 1.6 0 0 0 0-2.3" />
      <path d="M13.5 12.3l1.3 1.3a1.6 1.6 0 0 0 2.3 0" />
    </IconBase>
  );
}

export function IconTools(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M14.5 9.5 19 5a3 3 0 0 1-4 4l-4.5 4.5" />
      <rect x="4" y="15.5" width="6" height="4.2" rx="1.6" transform="rotate(-45 7 17.6)" />
      <path d="M9.5 14.5 5 19" />
    </IconBase>
  );
}

export function IconUsers(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
      <circle cx="17.5" cy="9" r="2.6" />
      <path d="M15.3 12.2a4.6 4.6 0 0 1 5.2 4.6" />
    </IconBase>
  );
}

export function IconFlagCheckered(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="6" y1="3.5" x2="6" y2="20.5" />
      <path d="M6 5h5l1.5 1.7L14 5h4v6h-4l-1.5-1.7L11 11H6Z" strokeLinejoin="round" />
    </IconBase>
  );
}

export function IconFlag(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="6" y1="3.5" x2="6" y2="20.5" />
      <path d="M6 5h11l-3 3.5 3 3.5H6Z" strokeLinejoin="round" />
    </IconBase>
  );
}

export function IconScroll(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M6 4h11a2 2 0 0 1 2 2v13" />
      <path d="M6 4a2 2 0 0 0-2 2v11.5A2.5 2.5 0 0 0 6.5 20H19a2 2 0 0 1-2-2V6" />
      <line x1="8" y1="8.5" x2="15" y2="8.5" />
      <line x1="8" y1="12" x2="15" y2="12" />
    </IconBase>
  );
}

export function IconBrain(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M9.5 4.5a3 3 0 0 0-3 3v.4A3 3 0 0 0 5 13a3 3 0 0 0 2 5.6 2.8 2.8 0 0 0 2.5 1.4A2.9 2.9 0 0 0 12 17V6.9a2.4 2.4 0 0 0-2.5-2.4Z" />
      <path d="M14.5 4.5a3 3 0 0 1 3 3v.4A3 3 0 0 1 19 13a3 3 0 0 1-2 5.6 2.8 2.8 0 0 1-2.5 1.4A2.9 2.9 0 0 1 12 17V6.9a2.4 2.4 0 0 1 2.5-2.4Z" />
    </IconBase>
  );
}

export function IconBomb(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="11" cy="15" r="7" />
      <line x1="11" y1="8" x2="12.5" y2="4.5" />
      <line x1="13.5" y1="0.8" x2="13.5" y2="4.8" />
      <line x1="11.7" y1="1.6" x2="15.3" y2="4" />
      <line x1="15.3" y1="1.6" x2="11.7" y2="4" />
    </IconBase>
  );
}

export function IconGloves(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M6 21v-6.5a3 3 0 0 1 3-3h.5v-4a1.5 1.5 0 0 1 3 0v4h1v-5a1.5 1.5 0 0 1 3 0v5h.5a1.5 1.5 0 0 1 1.5 1.5V16" strokeLinejoin="round" />
      <path d="M6 21h12v-3.5a2 2 0 0 0-2-2h-8" strokeLinejoin="round" />
    </IconBase>
  );
}

export function IconGoal(props: IconProps) {
  return (
    <IconBase {...props}>
      <line x1="5" y1="6" x2="19" y2="6" />
      <line x1="5" y1="6" x2="5" y2="19" />
      <line x1="19" y1="6" x2="19" y2="19" />
      <line x1="5" y1="12.5" x2="19" y2="12.5" opacity="0.45" />
      <line x1="10.3" y1="6" x2="10.3" y2="18" opacity="0.45" />
      <line x1="13.7" y1="6" x2="13.7" y2="18" opacity="0.45" />
    </IconBase>
  );
}

export function IconShirt(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M9 4 4 7l2 3 2-1v11h8V9l2 1 2-3-5-3a2.5 2.5 0 0 1-5 0Z" strokeLinejoin="round" />
    </IconBase>
  );
}

export function IconStadium(props: IconProps) {
  return (
    <IconBase {...props}>
      <ellipse cx="12" cy="12" rx="9" ry="5.5" />
      <ellipse cx="12" cy="12" rx="4.5" ry="2.6" />
      <line x1="3" y1="12" x2="1.5" y2="12" />
      <line x1="21" y1="12" x2="22.5" y2="12" />
    </IconBase>
  );
}

export function IconTag(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12.5 4H6a2 2 0 0 0-2 2v6.5a2 2 0 0 0 .6 1.4l8 8a2 2 0 0 0 2.8 0l6-6a2 2 0 0 0 0-2.8l-8-8a2 2 0 0 0-1.4-.6Z" strokeLinejoin="round" />
      <circle cx="8.5" cy="8.5" r="1.4" />
    </IconBase>
  );
}

export function IconCard(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="7" y="3" width="10" height="18" rx="2" />
    </IconBase>
  );
}

export function IconBoot(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M8 3v7.5L4 15v3.5A1.5 1.5 0 0 0 5.5 20h14a1.5 1.5 0 0 0 1.4-2L18 12.5A4 4 0 0 0 14.5 10H12V3Z" strokeLinejoin="round" />
      <line x1="4" y1="15" x2="12" y2="15" />
    </IconBase>
  );
}

export function IconUpgrade(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect x="5" y="3" width="14" height="18" rx="3" />
      <polyline points="9,13.5 12,9.5 15,13.5" />
      <line x1="12" y1="9.5" x2="12" y2="17" />
    </IconBase>
  );
}

export function IconClock(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8" />
      <polyline points="12,7.5 12,12 15.2,14" />
    </IconBase>
  );
}

export function IconInboxEmpty(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 12.5 6.5 5h11L20 12.5" strokeLinejoin="round" />
      <path d="M4 12.5v5A1.5 1.5 0 0 0 5.5 19h13a1.5 1.5 0 0 0 1.5-1.5v-5" />
      <path d="M4 12.5h4.5l1 2h5l1-2H20" />
    </IconBase>
  );
}

export function IconChat(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8A2.5 2.5 0 0 1 17.5 16H10l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5Z" strokeLinejoin="round" />
      <line x1="8" y1="7.8" x2="16" y2="7.8" />
      <line x1="8" y1="11" x2="13" y2="11" />
    </IconBase>
  );
}
