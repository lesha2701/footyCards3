import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "@/components/layout/AppLayout";
import AdminGuard from "@/admin/AdminGuard";
import AdminLayout from "@/admin/AdminLayout";
import AdminDashboardPage from "@/admin/pages/AdminDashboardPage";
import AdminUsersPage from "@/admin/pages/AdminUsersPage";
import AdminPlayersPage from "@/admin/pages/AdminPlayersPage";
import AdminPacksPage from "@/admin/pages/AdminPacksPage";
import AdminTradesPage from "@/admin/pages/AdminTradesPage";
import AdminGamesPage from "@/admin/pages/AdminGamesPage";
import AdminLogPage from "@/admin/pages/AdminLogPage";
import HomePage from "@/pages/HomePage";
import PacksPage from "@/pages/PacksPage";
import PackOpenPage from "@/pages/PackOpenPage";
import PlayPage from "@/pages/PlayPage";
import MemoryGamePage from "@/pages/MemoryGamePage";
import ArenaPage from "@/pages/ArenaPage";
import CollectionPage from "@/pages/CollectionPage";
import TradesPage from "@/pages/TradesPage";
import NewTradePage from "@/pages/NewTradePage";
import ProfilePage from "@/pages/ProfilePage";
import PublicProfilePage from "@/pages/PublicProfilePage";
import LoadingScreen from "@/components/common/LoadingScreen";
import ErrorScreen from "@/components/common/ErrorScreen";
import { createSession } from "@/api/auth";
import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";
import { getTelegramColorScheme, initTelegramApp, isInsideTelegram } from "@/lib/telegram";
import { ApiRequestError } from "@/lib/api";

export default function App() {
  const { setUser, setAdminToken, setReady, isReady } = useAuthStore();
  const setTheme = useUiStore((s) => s.setTheme);
  const theme = useUiStore((s) => s.theme);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    initTelegramApp();
    if (isInsideTelegram()) {
      setTheme(getTelegramColorScheme());
    } else {
      setTheme(theme);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    createSession()
      .then((res) => {
        if (cancelled) return;
        setUser(res.user);
        setAdminToken(res.admin_token);
        setReady(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof ApiRequestError ? err.message : "Не удалось подключиться к серверу";
        setError(message);
      });
    return () => {
      cancelled = true;
    };
  }, [setUser, setAdminToken, setReady]);

  if (error) return <ErrorScreen message={error} />;
  if (!isReady) return <LoadingScreen />;

  return (
    <Routes>
      <Route path="/admin" element={<AdminGuard><AdminLayout /></AdminGuard>}>
        <Route index element={<AdminDashboardPage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="players" element={<AdminPlayersPage />} />
        <Route path="packs" element={<AdminPacksPage />} />
        <Route path="trades" element={<AdminTradesPage />} />
        <Route path="games" element={<AdminGamesPage />} />
        <Route path="log" element={<AdminLogPage />} />
      </Route>

      <Route path="/packs/:packId/open" element={<PackOpenPage />} />

      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/packs" element={<PacksPage />} />
        <Route path="/play" element={<PlayPage />} />
        <Route path="/play/memory" element={<MemoryGamePage />} />
        <Route path="/play/arena" element={<ArenaPage />} />
        <Route path="/collection" element={<CollectionPage />} />
        <Route path="/trades" element={<TradesPage />} />
        <Route path="/trades/new" element={<NewTradePage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/users/:userId" element={<PublicProfilePage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
