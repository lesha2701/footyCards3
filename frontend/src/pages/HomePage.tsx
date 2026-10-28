import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchFeatureFlags } from "@/api/featureFlags";
import { fetchLeagueStatus } from "@/api/leagues";
import { fetchMyProfile } from "@/api/profile";
import { fetchWheelStatus } from "@/api/wheel";
import HomeHero from "@/components/home/HomeHero";
import ModesGrid from "@/components/home/ModesGrid";
import ShowcaseCard from "@/components/home/ShowcaseCard";
import TodayCard from "@/components/home/TodayCard";
import NewbieCard from "@/components/newbie/NewbieCard";
import { StarterOfferBanner, StarterOfferModal } from "@/components/shop/StarterOffer";
import { IconChevronRight, IconHandshake, type IconProps } from "@/components/icons";

export default function HomePage() {
  const navigate = useNavigate();

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: wheelStatus } = useQuery({ queryKey: ["wheel-status"], queryFn: fetchWheelStatus });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });
  const { data: leagueStatus } = useQuery({ queryKey: ["league-status"], queryFn: fetchLeagueStatus });

  return (
    <div className="flex flex-col gap-5">
      <HomeHero profile={profile} league={leagueStatus} leaguesEnabled={flags?.leagues_enabled !== false} />

      <NewbieCard />

      <StarterOfferModal />
      <StarterOfferBanner hideable />
      {profile?.referral_reward_pending && (
        <NoticeCard
          Icon={IconHandshake}
          title="Тебя пригласил друг!"
          subtitle={`Поиграй ${profile.referral_active_days ?? 3} дня — и получишь ${profile.referral_referred_reward.toLocaleString("ru-RU")} монет`}
          onClick={() => navigate("/packs")}
        />
      )}

      <TodayCard wheel={flags?.wheel_enabled !== false ? wheelStatus : null} />

      <ModesGrid />

      <ShowcaseCard />
    </div>
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
