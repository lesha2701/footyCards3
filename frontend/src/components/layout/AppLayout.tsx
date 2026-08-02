import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import LeaveConfirmDialog from "@/components/common/LeaveConfirmDialog";
import BottomNav from "@/components/layout/BottomNav";
import TopBar from "@/components/layout/TopBar";
import { useMatchGuardStore } from "@/store/matchGuardStore";

export default function AppLayout() {
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (useMatchGuardStore.getState().active) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
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
