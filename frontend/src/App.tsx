import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import AppLayout from "@/components/layout/AppLayout";
import AdminGuard from "@/admin/AdminGuard";
import AdminLayout from "@/admin/AdminLayout";
import AdminDashboardPage from "@/admin/pages/AdminDashboardPage";
import AdminUsersPage from "@/admin/pages/AdminUsersPage";
import AdminPlayersPage from "@/admin/pages/AdminPlayersPage";
import AdminPacksPage from "@/admin/pages/AdminPacksPage";
import AdminCardCollectionsPage from "@/admin/pages/AdminCardCollectionsPage";
import AdminTasksPage from "@/admin/pages/AdminTasksPage";
import AdminTradesPage from "@/admin/pages/AdminTradesPage";
import AdminTrophiesPage from "@/admin/pages/AdminTrophiesPage";
import AdminGiftsPage from "@/admin/pages/AdminGiftsPage";
import AdminWheelPage from "@/admin/pages/AdminWheelPage";
import AdminGamesPage from "@/admin/pages/AdminGamesPage";
import AdminUpgradesPage from "@/admin/pages/AdminUpgradesPage";
import AdminShopPage from "@/admin/pages/AdminShopPage";
import AdminBroadcastsPage from "@/admin/pages/AdminBroadcastsPage";
import AdminLogPage from "@/admin/pages/AdminLogPage";
import HomePage from "@/pages/HomePage";
import WheelPage from "@/pages/WheelPage";
import PacksPage from "@/pages/PacksPage";
import PackOpenPage from "@/pages/PackOpenPage";
import PlayPage from "@/pages/PlayPage";
import MemoryGamePage from "@/pages/MemoryGamePage";
import ArenaPage from "@/pages/ArenaPage";
import TacticoMatchesPage from "@/pages/TacticoMatchesPage";
import TacticoMatchPage from "@/pages/TacticoMatchPage";
import TacticoSearchPage from "@/pages/TacticoSearchPage";
import TacticoSquadPage from "@/pages/TacticoSquadPage";
import SaboteurGamePage from "@/pages/SaboteurGamePage";
import PenaltyGamePage from "@/pages/PenaltyGamePage";
import PenaltyMatchesPage from "@/pages/PenaltyMatchesPage";
import PenaltyMatchPage from "@/pages/PenaltyMatchPage";
import PenaltySearchPage from "@/pages/PenaltySearchPage";
import FreeKickGamePage from "@/pages/FreeKickGamePage";
import HangmanGamePage from "@/pages/HangmanGamePage";
import PairsGamePage from "@/pages/PairsGamePage";
import CollectionPage from "@/pages/CollectionPage";
import TradesPage from "@/pages/TradesPage";
import NewTradePage from "@/pages/NewTradePage";
import TasksPage from "@/pages/TasksPage";
import UpgradePage from "@/pages/UpgradePage";
import RankingPage from "@/pages/RankingPage";
import LeaguePage from "@/pages/LeaguePage";
import ProfilePage from "@/pages/ProfilePage";
import GiftsPage from "@/pages/GiftsPage";
import PublicProfilePage from "@/pages/PublicProfilePage";
import LoadingScreen from "@/components/common/LoadingScreen";
import ErrorScreen from "@/components/common/ErrorScreen";
import OnboardingScreen from "@/components/common/OnboardingScreen";
import { createSession } from "@/api/auth";
import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";
import { getTelegramColorScheme, initTelegramApp, isInsideTelegram } from "@/lib/telegram";
import { ApiRequestError } from "@/lib/api";
import { hasSeenOnboarding, markOnboardingSeen } from "@/lib/onboarding";

function PenaltySearchRoute() {
  const location = useLocation();
  const userCardId = (location.state as { userCardId?: number } | null)?.userCardId;
  if (!userCardId) return <Navigate to="/play/penalty/matches" replace />;
  return <PenaltySearchPage userCardId={userCardId} />;
}

export default function App() {
  const { user, setUser, setAdminToken, setReady, isReady } = useAuthStore();
  const setTheme = useUiStore((s) => s.setTheme);
  const theme = useUiStore((s) => s.theme);
  const [error, setError] = useState<string | null>(null);
  const [onboardingSeen, setOnboardingSeen] = useState(true);

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
    const referralCode = new URLSearchParams(window.location.search).get("ref") ?? undefined;
    createSession(referralCode)
      .then((res) => {
        if (cancelled) return;
        setUser(res.user);
        setAdminToken(res.admin_token);
        setOnboardingSeen(hasSeenOnboarding(res.user.id));
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

  if (user && !onboardingSeen) {
    return (
      <OnboardingScreen
        onFinish={() => {
          markOnboardingSeen(user.id);
          setOnboardingSeen(true);
        }}
      />
    );
  }

  return (
    <Routes>
      <Route path="/admin" element={<AdminGuard><AdminLayout /></AdminGuard>}>
        <Route index element={<AdminDashboardPage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="players" element={<AdminPlayersPage />} />
        <Route path="packs" element={<AdminPacksPage />} />
        <Route path="card-collections" element={<AdminCardCollectionsPage />} />
        <Route path="tasks" element={<AdminTasksPage />} />
        <Route path="trades" element={<AdminTradesPage />} />
        <Route path="trophies" element={<AdminTrophiesPage />} />
        <Route path="gifts" element={<AdminGiftsPage />} />
        <Route path="wheel" element={<AdminWheelPage />} />
        <Route path="games" element={<AdminGamesPage />} />
        <Route path="upgrades" element={<AdminUpgradesPage />} />
        <Route path="shop" element={<AdminShopPage />} />
        <Route path="broadcasts" element={<AdminBroadcastsPage />} />
        <Route path="log" element={<AdminLogPage />} />
      </Route>

      <Route path="/packs/:packId/open" element={<PackOpenPage />} />

      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/packs" element={<PacksPage />} />
        <Route path="/play" element={<PlayPage />} />
        <Route path="/play/memory" element={<MemoryGamePage />} />
        <Route path="/play/arena" element={<ArenaPage />} />
        <Route path="/play/tactico" element={<TacticoMatchesPage />} />
        <Route path="/play/tactico/squad" element={<TacticoSquadPage />} />
        <Route path="/play/tactico/search" element={<TacticoSearchPage />} />
        <Route path="/play/tactico/matches/:matchId" element={<TacticoMatchPage />} />
        <Route path="/play/saboteur" element={<SaboteurGamePage />} />
        <Route path="/play/penalty" element={<PenaltyGamePage />} />
        <Route path="/play/penalty/matches" element={<PenaltyMatchesPage />} />
        <Route path="/play/penalty/matches/search" element={<PenaltySearchRoute />} />
        <Route path="/play/penalty/matches/:matchId" element={<PenaltyMatchPage />} />
        <Route path="/play/free-kick" element={<FreeKickGamePage />} />
        <Route path="/play/hangman" element={<HangmanGamePage />} />
        <Route path="/play/pairs" element={<PairsGamePage />} />
        <Route path="/collection" element={<CollectionPage />} />
        <Route path="/trades" element={<TradesPage />} />
        <Route path="/trades/new" element={<NewTradePage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/wheel" element={<WheelPage />} />
        <Route path="/upgrade" element={<UpgradePage />} />
        <Route path="/ranking" element={<RankingPage />} />
        <Route path="/league" element={<LeaguePage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/gifts" element={<GiftsPage />} />
        <Route path="/users/:userId" element={<PublicProfilePage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
