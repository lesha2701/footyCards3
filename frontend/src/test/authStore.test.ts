import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "@/store/authStore";
import type { UserMe } from "@/types";

const baseUser: UserMe = {
  id: 1,
  telegram_id: 123,
  username: "tester",
  first_name: "Test",
  last_name: null,
  avatar_url: null,
  balance: 500,
  is_admin: false,
  level: 1,
  experience: 0,
  arena_rating: 1000,
  matches_won: 0,
  matches_drawn: 0,
  matches_lost: 0,
  memory_best_score: 0,
  match_energy: 10,
  created_at: new Date().toISOString(),
};

describe("authStore", () => {
  beforeEach(() => {
    useAuthStore.getState().reset();
  });

  it("starts with no user and not ready", () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isReady).toBe(false);
  });

  it("setUser stores the user", () => {
    useAuthStore.getState().setUser(baseUser);
    expect(useAuthStore.getState().user?.balance).toBe(500);
  });

  it("updateBalance only mutates the balance field", () => {
    useAuthStore.getState().setUser(baseUser);
    useAuthStore.getState().updateBalance(750);
    const user = useAuthStore.getState().user;
    expect(user?.balance).toBe(750);
    expect(user?.username).toBe("tester");
  });

  it("updateBalance is a no-op when there is no user yet", () => {
    useAuthStore.getState().updateBalance(999);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("reset clears user and admin token", () => {
    useAuthStore.getState().setUser(baseUser);
    useAuthStore.getState().setAdminToken("token123");
    useAuthStore.getState().reset();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().adminToken).toBeNull();
  });
});
