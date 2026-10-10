import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import AppLayout from "@/components/layout/AppLayout";
import HomePage from "@/pages/HomePage";
import LoadingScreen from "@/components/common/LoadingScreen";
import ErrorScreen from "@/components/common/ErrorScreen";
import OnboardingScreen from "@/components/common/OnboardingScreen";
import { createSession } from "@/api/auth";
import { joinByInvite } from "@/api/clubs";
import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";
import { getTelegramWebApp, initTelegramApp } from "@/lib/telegram";
import { ApiRequestError } from "@/lib/api";
import { hasSeenOnboarding, markOnboardingSeen } from "@/lib/onboarding";
import { useTelegramBackButton } from "@/lib/useTelegramBackButton";

// Every screen except the landing page is split into its own chunk and
// fetched on first visit — players never download the admin panel, and the
// first load in Telegram only pays for what the home screen needs.
const AdminGuard = lazy(() => import("@/admin/AdminGuard"));
const AdminLayout = lazy(() => import("@/admin/AdminLayout"));
const AdminDashboardPage = lazy(() => import("@/admin/pages/AdminDashboardPage"));
const AdminUsersPage = lazy(() => import("@/admin/pages/AdminUsersPage"));
const AdminPlayersPage = lazy(() => import("@/admin/pages/AdminPlayersPage"));
const AdminCoachesPage = lazy(() => import("@/admin/pages/AdminCoachesPage"));
const AdminStadiumsPage = lazy(() => import("@/admin/pages/AdminStadiumsPage"));
const AdminPacksPage = lazy(() => import("@/admin/pages/AdminPacksPage"));
const AdminClubPacksPage = lazy(() => import("@/admin/pages/AdminClubPacksPage"));
const AdminClubsPage = lazy(() => import("@/admin/pages/AdminClubsPage"));
const AdminTournamentsPage = lazy(() => import("@/admin/pages/AdminTournamentsPage"));
const AdminCardCollectionsPage = lazy(() => import("@/admin/pages/AdminCardCollectionsPage"));
const AdminTasksPage = lazy(() => import("@/admin/pages/AdminTasksPage"));
const AdminTradesPage = lazy(() => import("@/admin/pages/AdminTradesPage"));
const AdminTrophiesPage = lazy(() => import("@/admin/pages/AdminTrophiesPage"));
const AdminLeaguesPage = lazy(() => import("@/admin/pages/AdminLeaguesPage"));
const AdminGiftsPage = lazy(() => import("@/admin/pages/AdminGiftsPage"));
const AdminDailyRewardsPage = lazy(() => import("@/admin/pages/AdminDailyRewardsPage"));
const AdminWheelPage = lazy(() => import("@/admin/pages/AdminWheelPage"));
const AdminGamesPage = lazy(() => import("@/admin/pages/AdminGamesPage"));
const AdminEconomyPage = lazy(() => import("@/admin/pages/AdminEconomyPage"));
const AdminUpgradesPage = lazy(() => import("@/admin/pages/AdminUpgradesPage"));
const AdminDiamondUpgradesPage = lazy(() => import("@/admin/pages/AdminDiamondUpgradesPage"));
const AdminCardSkillsPage = lazy(() => import("@/admin/pages/AdminCardSkillsPage"));
const AdminBingoPage = lazy(() => import("@/admin/pages/AdminBingoPage"));
const AdminShopPage = lazy(() => import("@/admin/pages/AdminShopPage"));
const AdminBroadcastsPage = lazy(() => import("@/admin/pages/AdminBroadcastsPage"));
const AdminLogPage = lazy(() => import("@/admin/pages/AdminLogPage"));
const WheelPage = lazy(() => import("@/pages/WheelPage"));
const PacksPage = lazy(() => import("@/pages/PacksPage"));
const PackOpenPage = lazy(() => import("@/pages/PackOpenPage"));
const PlayPage = lazy(() => import("@/pages/PlayPage"));
const MemoryGamePage = lazy(() => import("@/pages/MemoryGamePage"));
const ArenaPage = lazy(() => import("@/pages/ArenaPage"));
const TacticoMatchesPage = lazy(() => import("@/pages/TacticoMatchesPage"));
const TacticoMatchPage = lazy(() => import("@/pages/TacticoMatchPage"));
const TacticoOpenChallengePage = lazy(() => import("@/pages/TacticoOpenChallengePage"));
const TacticoSearchPage = lazy(() => import("@/pages/TacticoSearchPage"));
const TacticoSquadPage = lazy(() => import("@/pages/TacticoSquadPage"));
const SaboteurGamePage = lazy(() => import("@/pages/SaboteurGamePage"));
const PenaltyGamePage = lazy(() => import("@/pages/PenaltyGamePage"));
const PenaltyMatchesPage = lazy(() => import("@/pages/PenaltyMatchesPage"));
const PenaltyMatchPage = lazy(() => import("@/pages/PenaltyMatchPage"));
const PenaltyOpenChallengePage = lazy(() => import("@/pages/PenaltyOpenChallengePage"));
const PenaltySearchPage = lazy(() => import("@/pages/PenaltySearchPage"));
const FreeKickGamePage = lazy(() => import("@/pages/FreeKickGamePage"));
const HangmanGamePage = lazy(() => import("@/pages/HangmanGamePage"));
const PairsGamePage = lazy(() => import("@/pages/PairsGamePage"));
const FutDraftGamePage = lazy(() => import("@/pages/FutDraftGamePage"));
const ClubCreatePage = lazy(() => import("@/pages/ClubCreatePage"));
const ClubGamePage = lazy(() => import("@/pages/ClubGamePage"));
const ClubGamesPage = lazy(() => import("@/pages/ClubGamesPage"));
const ClubPenaltyPage = lazy(() => import("@/pages/ClubPenaltyPage"));
const ClubPositionMatchGamePage = lazy(() => import("@/pages/ClubPositionMatchGamePage"));
const ClubsPage = lazy(() => import("@/pages/ClubsPage"));
const TournamentMatchPage = lazy(() => import("@/pages/TournamentMatchPage"));
const TournamentPage = lazy(() => import("@/pages/TournamentPage"));
const ClubActivityPage = lazy(() => import("@/pages/ClubActivityPage"));
const ClubStatsPage = lazy(() => import("@/pages/ClubStatsPage"));
const ClubSquadPage = lazy(() => import("@/pages/ClubSquadPage"));
const ClubPacksPage = lazy(() => import("@/pages/ClubPacksPage"));
const ClubPackOpenPage = lazy(() => import("@/pages/ClubPackOpenPage"));
const CollectionPage = lazy(() => import("@/pages/CollectionPage"));
const TradesPage = lazy(() => import("@/pages/TradesPage"));
const NewTradePage = lazy(() => import("@/pages/NewTradePage"));
const TradeDetailPage = lazy(() => import("@/pages/TradeDetailPage"));
const TasksPage = lazy(() => import("@/pages/TasksPage"));
const UpgradePage = lazy(() => import("@/pages/UpgradePage"));
const BingoPage = lazy(() => import("@/pages/BingoPage"));
const RankingPage = lazy(() => import("@/pages/RankingPage"));
const ClubLeaderboardPage = lazy(() => import("@/pages/ClubLeaderboardPage"));
const PlayerTournamentPage = lazy(() => import("@/pages/PlayerTournamentPage"));
const PlayerTournamentRatingPage = lazy(() => import("@/pages/PlayerTournamentRatingPage"));
const PlayerTournamentStatsPage = lazy(() => import("@/pages/PlayerTournamentStatsPage"));
const PlayerTournamentSquadPage = lazy(() => import("@/pages/PlayerTournamentSquadPage"));
const PlayerTournamentDetailPage = lazy(() => import("@/pages/PlayerTournamentDetailPage"));
const PlayerTournamentMatchPage = lazy(() => import("@/pages/PlayerTournamentMatchPage"));
const LeaguePage = lazy(() => import("@/pages/LeaguePage"));
const ProfilePage = lazy(() => import("@/pages/ProfilePage"));
const GiftsPage = lazy(() => import("@/pages/GiftsPage"));
const PublicProfilePage = lazy(() => import("@/pages/PublicProfilePage"));

function PenaltySearchRoute() {
  const location = useLocation();
  const userCardId = (location.state as { userCardId?: number } | null)?.userCardId;
  if (!userCardId) return <Navigate to="/play/penalty/matches" replace />;
  return <PenaltySearchPage userCardId={userCardId} />;
}

export default function App() {
  const { user, setUser, setAdminToken, setReady, isReady } = useAuthStore();
  const syncTheme = useUiStore((s) => s.syncTheme);
  const [error, setError] = useState<string | null>(null);
  const [onboardingSeen, setOnboardingSeen] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    initTelegramApp();
    // "Авто" follows Telegram's light/dark switch live, no reload needed.
    syncTheme();
    const webApp = getTelegramWebApp();
    webApp?.onEvent("themeChanged", syncTheme);
    return () => webApp?.offEvent("themeChanged", syncTheme);
  }, [syncTheme]);

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

  useEffect(() => {
    if (!isReady || !user) return;
    const joinClubCode = new URLSearchParams(window.location.search).get("joinClub");
    if (!joinClubCode) return;
    joinByInvite(joinClubCode)
      .catch(() => undefined)
      .finally(() => {
        const url = new URL(window.location.href);
        url.searchParams.delete("joinClub");
        window.history.replaceState({}, "", url.toString());
        navigate("/clubs", { replace: true });
      });
  }, [isReady, user, navigate]);

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
    <Suspense fallback={<LoadingScreen />}>
    <TelegramBackButton />
    <Routes>
      <Route path="/admin" element={<AdminGuard><AdminLayout /></AdminGuard>}>
        <Route index element={<AdminDashboardPage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="players" element={<AdminPlayersPage />} />
        <Route path="coaches" element={<AdminCoachesPage />} />
        <Route path="stadiums" element={<AdminStadiumsPage />} />
        <Route path="packs" element={<AdminPacksPage />} />
        <Route path="club-packs" element={<AdminClubPacksPage />} />
        <Route path="clubs" element={<AdminClubsPage />} />
        <Route path="tournaments" element={<AdminTournamentsPage />} />
        <Route path="card-collections" element={<AdminCardCollectionsPage />} />
        <Route path="tasks" element={<AdminTasksPage />} />
        <Route path="trades" element={<AdminTradesPage />} />
        <Route path="trophies" element={<AdminTrophiesPage />} />
        <Route path="leagues" element={<AdminLeaguesPage />} />
        <Route path="gifts" element={<AdminGiftsPage />} />
        <Route path="wheel" element={<AdminWheelPage />} />
        <Route path="daily-rewards" element={<AdminDailyRewardsPage />} />
        <Route path="games" element={<AdminGamesPage />} />
        <Route path="economy" element={<AdminEconomyPage />} />
        <Route path="upgrades" element={<AdminUpgradesPage />} />
        <Route path="diamond-upgrades" element={<AdminDiamondUpgradesPage />} />
        <Route path="card-skills" element={<AdminCardSkillsPage />} />
        <Route path="bingo" element={<AdminBingoPage />} />
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
        <Route path="/play/tactico/open/:matchId" element={<TacticoOpenChallengePage />} />
        <Route path="/play/saboteur" element={<SaboteurGamePage />} />
        <Route path="/play/penalty" element={<PenaltyGamePage />} />
        <Route path="/play/penalty/matches" element={<PenaltyMatchesPage />} />
        <Route path="/play/penalty/matches/search" element={<PenaltySearchRoute />} />
        <Route path="/play/penalty/matches/:matchId" element={<PenaltyMatchPage />} />
        <Route path="/play/penalty/open/:matchId" element={<PenaltyOpenChallengePage />} />
        <Route path="/play/free-kick" element={<FreeKickGamePage />} />
        <Route path="/play/hangman" element={<HangmanGamePage />} />
        <Route path="/play/pairs" element={<PairsGamePage />} />
        <Route path="/play/fut-draft" element={<FutDraftGamePage />} />
        <Route path="/collection" element={<CollectionPage />} />
        <Route path="/trades" element={<TradesPage />} />
        <Route path="/trades/new" element={<NewTradePage />} />
        <Route path="/trades/:id" element={<TradeDetailPage />} />
        <Route path="/clubs" element={<ClubsPage />} />
        <Route path="/clubs/create" element={<ClubCreatePage />} />
        <Route path="/clubs/squad" element={<ClubSquadPage />} />
        <Route path="/clubs/activity" element={<ClubActivityPage />} />
        <Route path="/clubs/stats" element={<ClubStatsPage />} />
        <Route path="/clubs/packs" element={<ClubPacksPage />} />
        <Route path="/clubs/packs/:packId/open" element={<ClubPackOpenPage />} />
        <Route path="/clubs/games" element={<ClubGamesPage />} />
        <Route path="/clubs/game" element={<ClubGamePage />} />
        <Route path="/clubs/penalty" element={<ClubPenaltyPage />} />
        <Route path="/clubs/position-match" element={<ClubPositionMatchGamePage />} />
        <Route path="/clubs/tournament/:id" element={<TournamentPage />} />
        <Route path="/clubs/tournament/:id/matches/:matchId" element={<TournamentMatchPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/wheel" element={<WheelPage />} />
        <Route path="/upgrade" element={<UpgradePage />} />
        <Route path="/bingo" element={<BingoPage />} />
        <Route path="/ranking" element={<RankingPage />} />
        <Route path="/clubs/leaderboard" element={<ClubLeaderboardPage />} />
        <Route path="/player-tournament" element={<PlayerTournamentPage />} />
        <Route path="/player-tournament/rating" element={<PlayerTournamentRatingPage />} />
        <Route path="/player-tournament/squad" element={<PlayerTournamentSquadPage />} />
        <Route path="/player-tournament/stats" element={<PlayerTournamentStatsPage />} />
        <Route path="/player-tournament/:id" element={<PlayerTournamentDetailPage />} />
        <Route path="/player-tournament/:id/matches/:matchId" element={<PlayerTournamentMatchPage />} />
        <Route path="/league" element={<LeaguePage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/gifts" element={<GiftsPage />} />
        <Route path="/users/:userId" element={<PublicProfilePage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
  );
}

function TelegramBackButton() {
  useTelegramBackButton();
  return null;
}
