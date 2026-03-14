import { http } from "./client";
import type {
  RulesetOut,
  RuleConflictOut,
} from "@/types/api";

export const rulesetsApi = {
  list: () =>
    http
      .get<{ items: RulesetOut[]; total: number }>("/rulesets")
      .then((r) => r.data.items),

  get: (id: string) =>
    http.get<RulesetOut>(`/rulesets/${id}`).then((r) => r.data),

  create: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return http
      .post<RulesetOut>("/rulesets", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },

  createJson: (data: Omit<RulesetOut, "id" | "content_hash" | "is_active" | "created_by" | "created_at" | "updated_at" | "schema_version"> & { rules: any[] }) =>
    http.post<RulesetOut>("/rulesets", data).then((r) => r.data),

  update: (id: string, data: Omit<RulesetOut, "id" | "content_hash" | "is_active" | "created_by" | "created_at" | "updated_at" | "schema_version"> & { rules: any[] }) =>
    http.put<RulesetOut>(`/rulesets/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    http.delete(`/rulesets/${id}`).then((r) => r.data),

  conflicts: (id: string) =>
    http
      .get<RuleConflictOut[]>(`/rulesets/${id}/conflicts`)
      .then((r) => r.data),

  activate: (id: string) =>
    http.post(`/rulesets/${id}/activate`).then((r) => r.data),

  deactivate: (id: string) =>
    http.post(`/rulesets/${id}/deactivate`).then((r) => r.data),
};
