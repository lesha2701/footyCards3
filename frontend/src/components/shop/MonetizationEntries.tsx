import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchClubPass, fetchSeasonPass } from "@/api/monetization";
import { IconChevronRight, IconStar, IconTicket, IconTrophy, type IconProps } from "@/components/icons";

function Entry({
  Icon, iconClass, title, subtitle, badge, onClick,
}: {
  Icon: (props: IconProps) => JSX.Element;
  iconClass: string;
  title: string;
  subtitle: string;
  badge?: string | null;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.99]"
    >
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${iconClass}`}>
        <Icon size={18} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-ink-chalk">{title}</span>
        <span className="block truncate text-xs text-ink-mist">{subtitle}</span>
      </span>
      {badge && (
        <span className="rounded-full bg-accent-lime px-2 py-0.5 font-mono text-micro font-bold text-bg-base">{badge}</span>
      )}
      <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
    </button>
  );
}

/** Entry points to «Клубный абонемент», «Сезонный пропуск» and «Стиль»
 * (profile and shop). */
export default function MonetizationEntries({ showStyle = true }: { showStyle?: boolean }) {
  const navigate = useNavigate();
  const { data: clubPass } = useQuery({ queryKey: ["club-pass"], queryFn: fetchClubPass });
  const { data: season } = useQuery({ queryKey: ["season-pass"], queryFn: fetchSeasonPass });

  return (
    <div className="flex flex-col gap-2">
      {clubPass?.enabled && (
        <Entry
          Icon={IconTicket}
          iconClass="bg-emerald-400/15 text-emerald-300"
          title="Клубный абонемент"
          subtitle={
            clubPass.is_active
              ? clubPass.daily_claimed_today ? "Активен · бонус на сегодня получен" : "Активен · забери ежедневный бонус"
              : `Бонусы каждый день · ${clubPass.stars_price} ⭐ в месяц`
          }
          badge={clubPass.is_active && !clubPass.daily_claimed_today ? "1" : null}
          onClick={() => navigate("/club-pass")}
        />
      )}
      {season?.enabled && (
        <Entry
          Icon={IconTrophy}
          iconClass="bg-purple-400/15 text-purple-300"
          title={`Сезонный пропуск · ${season.name}`}
          subtitle={`Уровень ${season.level} · ${season.xp} XP${season.locked_premium ? ` · ${season.locked_premium} премиум-наград ждут` : ""}`}
          badge={season.claimable ? String(season.claimable) : null}
          onClick={() => navigate("/season")}
        />
      )}
      {showStyle && (
        <Entry
          Icon={IconStar}
          iconClass="bg-amber-400/15 text-amber-300"
          title="Стиль"
          subtitle="Рамки, фоны профиля и скины карточек"
          onClick={() => navigate("/style")}
        />
      )}
    </div>
  );
}
