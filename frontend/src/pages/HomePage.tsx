import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchCurrentBingo } from "@/api/bingo";
import { fetchFeatureFlags } from "@/api/featureFlags";
import { fetchLeagueStatus } from "@/api/leagues";
import { fetchMyProfile } from "@/api/profile";
import { fetchWheelStatus } from "@/api/wheel";
import HomeHero from "@/components/home/HomeHero";
import ModesGrid from "@/components/home/ModesGrid";
import ShowcaseCard from "@/components/home/ShowcaseCard";
import TodayCard from "@/components/home/TodayCard";
import WeeklyEventStrip from "@/components/home/WeeklyEventStrip";
import { StarterOfferBanner, StarterOfferModal } from "@/components/shop/StarterOffer";
import {
  IconChat,
  IconChevronRight,
  IconHandshake,
  type IconProps,
} from "@/components/icons";
import { haptic, openTelegramLink } from "@/lib/telegram";

const CHAT_INVITE_LINK = "https://t.me/+42EZisiOi8w1ZmMy";

export default function HomePage() {
  const navigate = useNavigate();

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: wheelStatus } = useQuery({ queryKey: ["wheel-status"], queryFn: fetchWheelStatus });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });
  const { data: leagueStatus } = useQuery({ queryKey: ["league-status"], queryFn: fetchLeagueStatus });
  const { data: bingo } = useQuery({ queryKey: ["bingo-current"], queryFn: fetchCurrentBingo });

  return (
    <div className="flex flex-col gap-5">
      <HomeHero profile={profile} league={leagueStatus} leaguesEnabled={flags?.leagues_enabled !== false} />

      <StarterOfferModal />
      <StarterOfferBanner hideable />
      {profile?.referral_reward_pending && (
        <NoticeCard
          Icon={IconHandshake}
          title="Тебя пригласил друг!"
          subtitle={`Открой любой пак (можно бесплатный) и получи ${profile.referral_referred_reward} монет`}
          onClick={() => navigate("/packs")}
        />
      )}

      <TodayCard wheel={flags?.wheel_enabled !== false ? wheelStatus : null} />

      <WeeklyEventStrip bingo={bingo} />

      <ModesGrid />

      <ShowcaseCard />

      <div className="flex flex-col gap-2">
        <SlimBanner
          Icon={IconChat}
          tint="bg-sky-400/15 text-sky-300"
          title="Чат VICTOR FC"
          subtitle="Обмены, дропы и паки по слову «вкарта»"
          onClick={() => {
            haptic("light");
            openTelegramLink(CHAT_INVITE_LINK);
          }}
        />
      </div>
    </div>
  );
}

function SlimBanner({
  Icon, tint, title, subtitle, onClick,
}: {
  Icon: (props: IconProps) => JSX.Element;
  tint: string;
  title: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button onClick={onClick} className="flex items-center gap-3 rounded-2xl bg-bg-surface px-3 py-2.5 text-left active:scale-[0.98]">
      <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${tint}`}>
        <Icon size={16} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-ink-chalk">{title}</span>
        <span className="block truncate text-xs text-ink-mist">{subtitle}</span>
      </span>
      <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
    </button>
  );
}

function NoticeCard({
  Icon,
  title,
  subtitle,
  onClick,
  disabled,
  trailingIcon: TrailingIcon,
}: {
  Icon: (props: IconProps) => JSX.Element;
  title: string;
  subtitle: string;
  onClick: () => void;
  disabled?: boolean;
  trailingIcon?: (props: IconProps) => JSX.Element;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-3 rounded-2xl bg-bg-surface px-4 py-3 text-left transition active:scale-[0.98] disabled:opacity-50"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-bg-raised text-accent-lime">
        <Icon size={18} />
      </div>
      <div className="flex-1">
        <p className="font-display text-sm font-bold text-ink-chalk">{title}</p>
        <p className="text-xs text-ink-mist">{subtitle}</p>
      </div>
      <span className="text-ink-mist-dim">
        {TrailingIcon ? <TrailingIcon size={16} /> : <IconChevronRight size={16} />}
      </span>
    </button>
  );
}
