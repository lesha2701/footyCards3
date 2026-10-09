import { useSearchParams } from "react-router-dom";

import AlbumTab from "@/components/collection/AlbumTab";
import MyCardsTab from "@/components/collection/MyCardsTab";
import SkillTokensStrip from "@/components/collection/SkillTokensStrip";
import CardsSectionTabs from "@/components/layout/CardsSectionTabs";

export default function CollectionPage() {
  // The tab lives in the URL (?tab=mine) so back/forward and the section
  // tabs shared with Обмены/Апгрейд land on the right screen.
  const [params] = useSearchParams();
  const tab = params.get("tab") === "mine" ? "mine" : "album";

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Карточки</h1>

      <CardsSectionTabs />

      <SkillTokensStrip />

      {tab === "album" ? <AlbumTab /> : <MyCardsTab />}
    </div>
  );
}
