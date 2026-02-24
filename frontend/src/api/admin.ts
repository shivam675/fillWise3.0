import { http } from "./client";
import type { UserOut, RoleEnum } from "@/types/api";

export const adminApi = {
  listUsers: () => http.get<UserOut[]>("/admin/users").then((r) => r.data),

  createUser: (data: {
    username: string;
    password: string;
    email?: string;
    role: RoleEnum;
  }) => http.post<UserOut>("/admin/users", data).then((r) => r.data),

  deleteUser: (id: string) =>
    http.delete(`/admin/users/${id}`).then((r) => r.data),
};
