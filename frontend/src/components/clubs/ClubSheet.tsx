import { AnimatePresence, motion, useDragControls, useReducedMotion } from "framer-motion";
import { Suspense, lazy, useEffect, type ComponentType } from "react";
import { createPortal } from "react-dom";

import { ListSkeleton } from "@/components/common/Skeleton";
import { ClubSheetContext } from "@/lib/clubSheet";
import type { ClubSheetKey } from "@/lib/clubTabs";

const PAGES: Record<ClubSheetKey, ComponentType> = {
  war: lazy(() => import("@/pages/ClubWarPage")),
  raid: lazy(() => import("@/pages/ClubRaidPage")),
  quests: lazy(() => import("@/pages/ClubQuestsPage")),
  league: lazy(() => import("@/pages/ClubLeaguePage")),
  games: lazy(() => import("@/pages/ClubGamesPage")),
  wall: lazy(() => import("@/pages/ClubWallPage")),
  shop: lazy(() => import("@/pages/ClubShopPage")),
  treasury: lazy(() => import("@/pages/ClubTreasuryPage")),
  activity: lazy(() => import("@/pages/ClubActivityPage")),
  stats: lazy(() => import("@/pages/ClubStatsPage")),
  leaderboard: lazy(() => import("@/pages/ClubLeaderboardPage")),
};
const Trophies = lazy(() => import("@/pages/ClubTrophiesPage"));

/** A club section sliding over the club home instead of a page transition.
 * It shows the section's own page, so the same screen also works as a full
 * page for a link from the bot. The sheet lives in the URL (`?sheet=`): the
 * back button closes it. Pull down by the handle, tap outside or the arrow. */
export function ClubSheet({ sheet, clubId, onClose }: { sheet: ClubSheetKey | "trophies" | null; clubId: number; onClose: () => void }) {
  const reduceMotion = useReducedMotion();
  const dragControls = useDragControls();

  useEffect(() => {
    if (!sheet) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [sheet]);

  const Page = sheet && sheet !== "trophies" ? PAGES[sheet] : null;
  return createPortal(
    <AnimatePresence>
      {sheet && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            className="flex h-[calc(100dvh-44px-env(safe-area-inset-top))] w-full max-w-lg flex-col rounded-t-3xl border border-white/10 bg-bg-base"
            initial={reduceMotion ? false : { y: "100%" }}
            animate={{ y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            drag="y"
            dragControls={dragControls}
            dragListener={false}
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.8 }}
            onDragEnd={(_, info) => { if (info.offset.y > 110 || info.velocity.y > 600) onClose(); }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="flex shrink-0 cursor-grab touch-none justify-center pb-2 pt-2.5"
              onPointerDown={(e) => dragControls.start(e)}
            >
              <span className="h-1 w-10 rounded-full bg-white/20" />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
              <ClubSheetContext.Provider value={{ close: onClose }}>
                <Suspense fallback={<ListSkeleton />}>
                  {Page ? <Page /> : <Trophies clubId={clubId} />}
                </Suspense>
              </ClubSheetContext.Provider>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
