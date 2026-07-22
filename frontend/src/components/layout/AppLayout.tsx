import { Outlet } from "react-router-dom";

import BottomNav from "@/components/layout/BottomNav";
import TopBar from "@/components/layout/TopBar";

export default function AppLayout() {
  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col bg-bg-base">
      <TopBar />
      <main className="flex-1 px-4 pb-24 pt-4">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
