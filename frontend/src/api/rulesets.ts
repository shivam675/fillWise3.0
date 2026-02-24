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

  conflicts: (id: string) =>
    http
      .get<RuleConflictOut[]>(`/rulesets/${id}/conflicts`)
      .then((r) => r.data),

  activate: (id: string) =>
    http.post(`/rulesets/${id}/activate`).then((r) => r.data),
};
