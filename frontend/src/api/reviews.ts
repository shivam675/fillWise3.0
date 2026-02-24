import { http } from "./client";
import type { ReviewOut, ReviewDecision } from "@/types/api";

const mapDecisionToStatus = (decision: ReviewDecision): string => {
  switch (decision) {
    case "approve":
      return "approved";
    case "reject":
      return "rejected";
    case "edit":
      return "edited";
    case "request_rerun":
      return "rerun_requested";
  }
};

export const reviewsApi = {
  getOrCreate: (rewriteId: string) =>
    http
      .get<ReviewOut>(`/reviews/rewrite/${rewriteId}`)
      .then((r) => r.data),

  decide: (
    reviewId: string,
    decision: ReviewDecision,
    options?: {
      editedText?: string;
      riskOverrideReason?: string;
    }
  ) =>
    http
      .post<ReviewOut>(`/reviews/${reviewId}/decide`, {
        status: mapDecisionToStatus(decision),
        edited_text: options?.editedText,
        risk_override_reason: options?.riskOverrideReason,
      })
      .then((r) => r.data),

  addComment: (reviewId: string, body: string, hunkIndex?: number, parentCommentId?: string) =>
    http
      .post(`/reviews/${reviewId}/comments`, {
        body,
        hunk_index: hunkIndex,
        parent_comment_id: parentCommentId,
      })
      .then((r) => r.data),
};
