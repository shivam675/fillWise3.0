import { http } from "./client";
import type { TokenResponse, UserOut } from "@/types/api";

export const authApi = {
  login: (username: string, password: string) =>
    http
      .post<TokenResponse>("/auth/login", { username, password })
      .then((r) => r.data),

  refresh: (refreshToken: string) =>
    http
      .post<TokenResponse>("/auth/refresh", { refresh_token: refreshToken })
      .then((r) => r.data),

  me: () => http.get<UserOut>("/auth/me").then((r) => r.data),

  changePassword: (currentPassword: string, newPassword: string) =>
    http
      .post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      })
      .then((r) => r.data),
};
