import { http } from "./client";
import type { AuditListResponse, ChainVerificationResult } from "@/types/api";

export const auditApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    actor_id?: string;
    entity_type?: string;
    entity_id?: string;
    event_type?: string;
  }) =>
    http
      .get<AuditListResponse>("/audit", { params })
      .then((r) => r.data),

  verify: () =>
    http
      .get<ChainVerificationResult>("/audit/verify")
      .then((r) => r.data),
};
