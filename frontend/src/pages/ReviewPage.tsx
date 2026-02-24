import { useState, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, X, Edit, RefreshCw, AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { reviewsApi } from "@/api/reviews";
import StatusBadge from "@/components/ui/StatusBadge";
import Spinner from "@/components/ui/Spinner";
import { extractErrorMessage } from "@/api/client";
import type { ReviewDecision } from "@/types/api";
import { cn } from "@/lib/utils";

/** Split text into pages of ~PAGE_CHARS characters, breaking at paragraph boundaries */
const PAGE_CHARS = 1200;

function splitIntoPages(text: string): string[] {
  if (!text) return [""];
  const paragraphs = text.split(/\n{2,}/);
  const pages: string[] = [];
  let current = "";
  for (const para of paragraphs) {
    if (current.length > 0 && current.length + para.length + 2 > PAGE_CHARS) {
      pages.push(current.trim());
      current = para;
    } else {
      current = current ? current + "\n\n" + para : para;
    }
  }
  if (current.trim()) pages.push(current.trim());
  return pages.length > 0 ? pages : [""];
}

export default function ReviewPage() {
  const { rewriteId } = useParams<{ rewriteId: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [pageIndex, setPageIndex] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [editedPages, setEditedPages] = useState<Record<number, string>>({});
  const [overrideReason, setOverrideReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [commentBody, setCommentBody] = useState("");

  const { data: review, isLoading, refetch } = useQuery({
    queryKey: ["reviews", rewriteId],
    queryFn: () => reviewsApi.getOrCreate(rewriteId!),
    enabled: !!rewriteId,
    staleTime: 0, // Always consider data stale to prevent cache issues
    refetchOnWindowFocus: true, // Refetch when window gains focus
  });

  const originalPages = useMemo(
    () => splitIntoPages(review?.original_text ?? ""),
    [review?.original_text],
  );
  const rewrittenPages = useMemo(
    () => splitIntoPages(review?.rewritten_text ?? review?.edited_text ?? ""),
    [review?.rewritten_text, review?.edited_text],
  );
  const totalPages = Math.max(originalPages.length, rewrittenPages.length);
  const safePageIndex = Math.min(pageIndex, totalPages - 1);

  const currentOriginal = originalPages[safePageIndex] ?? "";
  const currentRewritten = editedPages[safePageIndex] ?? rewrittenPages[safePageIndex] ?? "";
  const hasEdits = Object.keys(editedPages).length > 0;
  const currentPageEdited = editedPages[safePageIndex] !== undefined;

  const noChangesOnPage =
    currentOriginal.trim() === (rewrittenPages[safePageIndex] ?? "").trim() &&
    !currentPageEdited;

  const decideMut = useMutation({
    mutationFn: (decision: ReviewDecision) => {
      // If there are per-page edits, assemble them into the full edited text
      let assembledEdit: string | undefined;
      if (decision === "edit" && hasEdits) {
        assembledEdit = rewrittenPages
          .map((p, i) => editedPages[i] ?? p)
          .join("\n\n");
      }
      return reviewsApi.decide(review!.id, decision, {
        editedText: assembledEdit,
        riskOverrideReason: overrideReason || undefined,
      });
    },
    onMutate: (decision) => {
      // Optimistic update to prevent UI from showing stale state
      const previousReview = qc.getQueryData(["reviews", rewriteId]);
      
      // Optimistically update the review status 
      qc.setQueryData(["reviews", rewriteId], (old: any) => {
        if (!old) return old;
        return {
          ...old,
          status: decision === "edit" ? "edited" : decision === "approve" ? "approved" : "rejected",
          reviewed_at: new Date().toISOString(),
        };
      });
      
      return { previousReview };
    },
    onSuccess: () => {
      // Refetch to get the authoritative state from server
      qc.invalidateQueries({ queryKey: ["reviews", rewriteId] });
      setActionError(null);
    },
    onError: (err: any, _variables, context) => {
      // Rollback optimistic update on error
      if (context?.previousReview) {
        qc.setQueryData(["reviews", rewriteId], context.previousReview);
      }
      
      // Handle 409 conflicts gracefully
      if (err?.response?.status === 409) {
        const errMsg = extractErrorMessage(err);
        const errorCode = err?.response?.data?.error?.code;
        if (errorCode === "REV_002") {
          // Review already decided — refresh to show current state
          setActionError("This review has already been decided. Refreshing...");
          qc.invalidateQueries({ queryKey: ["reviews", rewriteId] });
          setTimeout(() => setActionError(null), 3000);
        } else {
          // Other 409 (e.g. risk override required) — show actual backend message
          setActionError(errMsg);
        }
      } else {
        setActionError(extractErrorMessage(err));
      }
    },
    retry: (failureCount, error: any) => {
      // Don't retry 409 conflicts or 422 validation errors
      if (error?.response?.status === 409 || error?.response?.status === 422) {
        return false;
      }
      return failureCount < 3;
    },
  });

  const commentMut = useMutation({
    mutationFn: () => reviewsApi.addComment(review!.id, commentBody),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reviews", rewriteId] });
      setCommentBody("");
    },
  });

  const criticalFindings = review?.risk_findings?.filter((r) => {
    const s = r.severity.toLowerCase();
    return s === "critical" || s === "high";
  }) ?? [];
  const needsOverride = criticalFindings.length > 0;

  if (isLoading) return <div className="flex justify-center py-20"><Spinner /></div>;
  if (!review) return <p className="text-gray-500">Review not found.</p>;

  const isPending = review.status === "pending" || review.status === "rerun_requested";

  const handleApprove = async () => {
    if (needsOverride && !overrideReason.trim()) {
      setActionError(
        "You must provide a risk override reason to approve a section with CRITICAL/HIGH findings."
      );
      return;
    }
    
    // Prevent duplicate submissions if already processing
    if (decideMut.isPending) {
      return;
    }
    
    setActionError(null); // Clear any previous errors
    
    try {
      // Pre-flight check: refetch the latest review data to ensure it's still pending
      const latestReview = await refetch();
      const currentReview = latestReview.data;
      
      if (!currentReview) {
        setActionError("Review not found. Please refresh the page.");
        return;
      }
      
      if (currentReview.status !== "pending" && currentReview.status !== "rerun_requested") {
        setActionError(`This review has already been decided (status: ${currentReview.status}). The page will refresh automatically.`);
        // Auto-refresh to show the current state
        setTimeout(() => {
          qc.invalidateQueries({ queryKey: ["reviews", rewriteId] });
          setActionError(null);
        }, 2000);
        return;
      }
      
      // Proceed with the decision
      decideMut.mutate(hasEdits ? "edit" : "approve");
    } catch (error) {
      console.error("Error checking review status:", error);
      setActionError("Failed to verify review status. Please try again.");
    }
  };

  const goTo = (idx: number) => {
    setEditMode(false);
    setPageIndex(Math.max(0, Math.min(idx, totalPages - 1)));
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="btn-ghost p-1">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Review</h1>
            <p className="text-sm text-gray-400">
              Rewrite ID: <span className="font-mono">{rewriteId?.slice(0, 8)}</span>
            </p>
          </div>
        </div>
        <StatusBadge status={review.status} />
      </div>

      {actionError && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      {/* Risk warnings */}
      {criticalFindings.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 space-y-2">
          <div className="flex items-center gap-2 text-red-700 font-medium text-sm">
            <AlertTriangle className="h-4 w-4" />
            Risk findings requiring review
          </div>
          {criticalFindings.map((f) => (
            <div key={f.id} className="flex items-start gap-2 text-sm">
              <StatusBadge status={f.severity} />
              <p className="text-red-700">{f.description}</p>
            </div>
          ))}
        </div>
      )}

      {/* Page navigation */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-4 py-2">
          <button
            className="btn-ghost p-1 disabled:opacity-40"
            disabled={safePageIndex === 0}
            onClick={() => goTo(safePageIndex - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <span>
              Page <span className="font-semibold">{safePageIndex + 1}</span> of {totalPages}
            </span>
            {editedPages[safePageIndex] !== undefined && (
              <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-xs text-yellow-700">
                Edited
              </span>
            )}
          </div>
          <button
            className="btn-ghost p-1 disabled:opacity-40"
            disabled={safePageIndex === totalPages - 1}
            onClick={() => goTo(safePageIndex + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Side-by-side canvas */}
      <div className="grid grid-cols-2 gap-4">
        {/* Left — Original */}
        <div className="card flex flex-col">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Original
          </h2>
          <pre className="flex-1 whitespace-pre-wrap text-sm text-gray-700 leading-relaxed">
            {currentOriginal || <span className="italic text-gray-300">(empty)</span>}
          </pre>
        </div>

        {/* Right — Suggested / Editable */}
        <div className="card flex flex-col">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              {currentPageEdited ? "Your edit" : "Suggested"}
            </h2>
            {isPending && (
              <button
                className="btn-ghost text-xs"
                onClick={() => setEditMode((p) => !p)}
              >
                <Edit className="h-3.5 w-3.5" />
                {editMode ? "Done" : "Edit"}
              </button>
            )}
          </div>

          {noChangesOnPage && !editMode ? (
            <div className="flex flex-1 items-center justify-center rounded-lg bg-gray-50 p-4">
              <p className="text-sm text-gray-400 italic">No changes on this page.</p>
            </div>
          ) : editMode ? (
            <textarea
              className="input flex-1 resize-none font-mono text-sm leading-relaxed"
              rows={14}
              value={currentRewritten}
              onChange={(e) => {
                setEditedPages((prev) => ({
                  ...prev,
                  [safePageIndex]: e.target.value,
                }));
              }}
            />
          ) : (
            <pre
              className={cn(
                "flex-1 whitespace-pre-wrap text-sm leading-relaxed",
                currentPageEdited ? "text-blue-700" : "text-gray-700"
              )}
            >
              {currentRewritten || <span className="italic text-gray-300">(empty)</span>}
            </pre>
          )}
        </div>
      </div>

      {/* Page-level inline approve hint when no changes */}
      {noChangesOnPage && !editMode && isPending && totalPages > 1 && (
        <p className="text-center text-xs text-gray-400">
          No changes detected on this page — use the arrows to continue or approve below.
        </p>
      )}

      {/* Override reason */}
      {needsOverride && isPending && (
        <div className="card border-red-200">
          <label className="label text-red-700">
            Risk override reason (required to approve)
          </label>
          <textarea
            className="input resize-none"
            rows={2}
            placeholder="Explain why it is safe to approve despite the above findings…"
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
          />
        </div>
      )}

      {/* Actions */}
      {isPending && (
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-primary"
            onClick={handleApprove}
            disabled={decideMut.isPending || !review}
          >
            <Check className="h-4 w-4" />
            {hasEdits ? "Approve with edits" : "Approve"}
          </button>
          {safePageIndex < totalPages - 1 && (
            <button
              className="btn-secondary"
              onClick={() => goTo(safePageIndex + 1)}
            >
              <ArrowRight className="h-4 w-4" />
              Next page
            </button>
          )}
          <button
            className="btn-secondary"
            onClick={() => {
              if (!decideMut.isPending) {
                setActionError(null);
                decideMut.mutate("request_rerun");
              }
            }}
            disabled={decideMut.isPending || (review.status !== "pending" && review.status !== "rerun_requested")}
          >
            <RefreshCw className="h-4 w-4" />
            Request re-run
          </button>
          <button
            className="btn-danger"
            onClick={() => {
              if (!decideMut.isPending) {
                setActionError(null);
                decideMut.mutate("reject");
              }
            }}
            disabled={decideMut.isPending || (review.status !== "pending" && review.status !== "rerun_requested")}
          >
            <X className="h-4 w-4" />
            Reject
          </button>
        </div>
      )}

      {/* Comments */}
      <div className="card">
        <h2 className="mb-4 font-semibold text-gray-800">Comments</h2>
        {review.comments.length === 0 ? (
          <p className="text-sm text-gray-400 mb-4">No comments yet.</p>
        ) : (
          <div className="space-y-3 mb-4">
            {review.comments.map((c) => (
              <div key={c.id} className="rounded-lg bg-gray-50 p-3 text-sm">
                <p className="font-medium text-gray-700">{c.author_id.slice(0, 8)}</p>
                <p className="mt-1 text-gray-600">{c.body}</p>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="Add a comment…"
            value={commentBody}
            onChange={(e) => setCommentBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && commentBody.trim()) {
                e.preventDefault();
                commentMut.mutate();
              }
            }}
          />
          <button
            className="btn-secondary"
            disabled={!commentBody.trim() || commentMut.isPending}
            onClick={() => commentMut.mutate()}
          >
            Post
          </button>
        </div>
      </div>
    </div>
  );
}