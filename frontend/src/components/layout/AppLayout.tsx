import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import LeaveConfirmDialog from "@/components/common/LeaveConfirmDialog";
import BottomNav from "@/components/layout/BottomNav";
import TopBar from "@/components/layout/TopBar";
import { apiUrl, buildAuthHeaders } from "@/lib/api";
import { useMatchGuardStore } from "@/store/matchGuardStore";

export default function AppLayout() {
  useEffect(() => {
    const beforeUnloadHandler = (e: BeforeUnloadEvent) => {
      if (useMatchGuardStore.getState().active) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    // `beforeunload` only shows the native "leave site?" prompt — it can't
    // tell us whether the user actually confirmed leaving, and a regular
    // axios call started there gets aborted before it reaches the network
    // once the page starts unloading. `pagehide` only fires once the page is
    // truly being torn down (i.e. after the user confirmed), so that's where
    // the forfeit is actually sent, via a keepalive fetch that survives the
    // unload.
    const pageHideHandler = (e: PageTransitionEvent) => {
      // `persisted` means the page is going into the back-forward cache (a
      // background/app-switch on mobile can trigger this), not actually
      // closing — it can still come back via `pageshow`. Only forfeit on a
      // real teardown, otherwise briefly switching away from the Telegram
      // Mini App mid-match would wrongly cost the player the match.
      if (e.persisted) return;
      const { active, forfeitPath } = useMatchGuardStore.getState();
      if (active && forfeitPath) {
        fetch(apiUrl(forfeitPath), { method: "POST", headers: buildAuthHeaders(), keepalive: true }).catch(() => {});
      }
    };
    window.addEventListener("beforeunload", beforeUnloadHandler);
    window.addEventListener("pagehide", pageHideHandler);
    return () => {
      window.removeEventListener("beforeunload", beforeUnloadHandler);
      window.removeEventListener("pagehide", pageHideHandler);
    };
  }, []);

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col bg-bg-base">
      <TopBar />
      <main className="flex-1 px-4 pb-24 pt-3">
        <Outlet />
      </main>
      <BottomNav />
      <LeaveConfirmDialog />
    </div>
  );
}
