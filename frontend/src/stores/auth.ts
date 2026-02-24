/**
 * Zustand auth store — persists tokens and current user in localStorage.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserOut } from "@/types/api";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserOut | null;

  setTokens: (accessToken: string, refreshToken: string) => void;
  setUser: (user: UserOut) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,

      setTokens: (accessToken, refreshToken) =>
        set({ accessToken, refreshToken }),

      setUser: (user) => set({ user }),

      logout: () =>
        set({ accessToken: null, refreshToken: null, user: null }),

      isAuthenticated: () => !!get().accessToken,
    }),
    {
      name: "fillwise-auth",
      // Only persist tokens; user profile re-fetched on mount.
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
);
