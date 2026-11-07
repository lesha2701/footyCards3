import { useNavigate } from "react-router-dom";

import { IconChevronLeft } from "@/components/icons";
import { useClubSheetContext } from "@/lib/clubSheet";

/** The header arrow of a club section: closes it when it is open as a sheet
 * over the club home, otherwise goes back to the club. */
export function ClubBackButton({ onBack }: { onBack?: () => void }) {
  const navigate = useNavigate();
  const sheet = useClubSheetContext();
  return (
    <button
      onClick={sheet ? sheet.close : onBack ?? (() => navigate("/clubs"))}
      className="rounded-full bg-bg-surface p-2 active:scale-95"
      aria-label={sheet ? "Закрыть" : "Назад"}
    >
      <IconChevronLeft size={18} className={`text-ink-chalk ${sheet ? "-rotate-90" : ""}`} />
    </button>
  );
}
