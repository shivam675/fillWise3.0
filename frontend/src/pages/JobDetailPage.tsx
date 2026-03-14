import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Zap, Check, Trash2, Square } from "lucide-react";
import { jobsApi } from "@/api/jobs";
import { http } from "@/api/client";
import StatusBadge from "@/components/ui/StatusBadge";
import Spinner from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";
import type { JobProgressUpdate, SectionRewriteOut } from "@/types/api";
import { extractErrorMessage } from "@/api/client";

const WS_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/^http/, "ws") ?? "";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { accessToken } = useAuthStore();

  const [streamLines, setStreamLines] = useState<string[]>([]);
  const [wsStatus, setWsStatus] = useState<"idle" | "live" | "done" | "error">("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const streamEndRef = useRef<HTMLDivElement>(null);
  const [assembleError, setAssembleError] = useState<string | null>(null);
  const [assembleSuccess, setAssembleSuccess] = useState(false);
  const [liveProgress, setLiveProgress] = useState<{ completed: number; total: number } | null>(null);
  const currentSectionRef = useRef<string | null>(null);

  const { data: job, isLoading } = useQuery({
    queryKey: ["jobs", id],
    queryFn: () => jobsApi.get(id!),
    enabled: !!id,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "running" || s === "pending" ? 2000 : false;
    },
  });

  const { data: rewrites } = useQuery({
    queryKey: ["jobs", id, "rewrites"],
    queryFn: () => jobsApi.rewrites(id!),
    enabled: !!id && job?.status === "completed",
  });

  const assembleMut = useMutation({
    mutationFn: async () => {
      // Trigger assembly — will fail fast if reviews are incomplete
      await jobsApi.assemble(id!);
      // Poll for the export file to be ready, then download it
      const docId = job!.document_id;
      const maxAttempts = 20;
      for (let i = 0; i < maxAttempts; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        try {
          await jobsApi.downloadExport(docId, id!);
          return; // download triggered successfully
        } catch {
          if (i === maxAttempts - 1) {
            throw new Error(
              "Assembly is taking longer than expected. Please try downloading again in a moment."
            );
          }
        }
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs", id] });
      setAssembleError(null);
      setAssembleSuccess(true);
      setTimeout(() => setAssembleSuccess(false), 4000);
    },
    onError: (err) => {
      setAssembleError(extractErrorMessage(err));
      setAssembleSuccess(false);
    },
  });

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const deleteMut = useMutation({
    mutationFn: () => jobsApi.delete(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      navigate("/jobs", { replace: true });
    },
    onError: (err) => setAssembleError(extractErrorMessage(err)),
  });

  const cancelMut = useMutation({
    mutationFn: () => jobsApi.cancel(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs", id] });
    },
    onError: (err) => setAssembleError(extractErrorMessage(err)),
  });

  // Connect WebSocket when job is pending or running to drive execution
  // and receive live token streaming
    const shouldConnect = job?.status === "pending" || job?.status === "running";

    useEffect(() => {
      if (!id || !accessToken || !shouldConnect) return;
    if (wsRef.current) return;

    let cancelled = false;

    // Obtain a short-lived WS ticket then connect
    (async () => {
      try {
        const { data } = await http.post<{ ticket: string }>("/auth/ws-ticket");
        if (cancelled) return;

        setWsStatus("live");
        setStreamLines([]);
        currentSectionRef.current = null;
        const ws = new WebSocket(
          `${WS_BASE}/api/v1/ws/jobs/${id}?ticket=${data.ticket}`
        );
        wsRef.current = ws;

        ws.onmessage = (e) => {
          const update: JobProgressUpdate = JSON.parse(e.data);

          // Track progress counts from the orchestrator
          if (update.total_sections > 0) {
            setLiveProgress({ completed: update.completed_sections, total: update.total_sections });
          }

          // When a new section starts, push a separator line
          if (update.section_id && update.section_id !== currentSectionRef.current && update.status === "running" && !update.token) {
            currentSectionRef.current = update.section_id;
            setStreamLines((prev) => [
              ...prev,
              `\n── Section ${(update.completed_sections || 0) + 1} of ${update.total_sections || "?"} ──`,
              "",
            ]);
          }

          if (update.token) {
            setStreamLines((prev) => {
              const last = prev[prev.length - 1] ?? "";
              return [...prev.slice(0, -1), last + update.token];
            });
          }
          if (update.done) {
            setWsStatus("done");
            setLiveProgress(null);
            qc.invalidateQueries({ queryKey: ["jobs", id] });
            ws.close();
          }
        };
        ws.onerror = () => setWsStatus("error");
        ws.onclose = () => {
          wsRef.current = null;
          if (wsStatus === "live") setWsStatus("done");
        };
      } catch {
        setWsStatus("error");
      }
    })();

    return () => {
      cancelled = true;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id, accessToken, shouldConnect]);

  if (isLoading || !job) return <Spinner />;

  const completed = liveProgress?.completed ?? job.completed_sections;
  const total = liveProgress?.total ?? job.total_sections;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)} className="btn-ghost p-1">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {job.name || "Untitled Job"} <span className="font-mono text-base text-gray-400">({job.id.slice(0, 8)})</span>
            </h1>
            <p className="text-sm text-gray-400">Created {formatDate(job.created_at)}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={job.status} />
          {job.status === "completed" && (
            <button
              className="btn-primary"
              onClick={() => assembleMut.mutate()}
              disabled={assembleMut.isPending}
            >
              {assembleMut.isPending ? (
                <Zap className="h-4 w-4 animate-pulse" />
              ) : assembleSuccess ? (
                <Check className="h-4 w-4" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              {assembleMut.isPending
                ? "Building & Downloading…"
                : assembleSuccess
                  ? "Downloaded!"
                  : "Assemble DOCX"}
            </button>
          )}
          {(job.status === "running" || job.status === "pending") && (
            <button
              className="btn-secondary text-amber-600 hover:text-amber-700"
              onClick={() => cancelMut.mutate()}
              disabled={cancelMut.isPending}
              title="Stop job"
            >
              <Square className="h-4 w-4" />
              {cancelMut.isPending ? "Stopping…" : "Stop"}
            </button>
          )}
          {job.status !== "running" && job.status !== "pending" && (
            <button
              className="btn-secondary text-red-600 hover:text-red-700"
              onClick={() => setShowDeleteConfirm(true)}
              title="Delete job"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
          )}
        </div>
      </div>

      {assembleError && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {assembleError}
        </div>
      )}

      {job.error_message && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
          <strong>Job error:</strong> {job.error_message}
        </div>
      )}

      {/* Progress */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">
            {completed} / {total} sections
          </span>
          <span className="text-sm text-gray-500">{pct}%</span>
        </div>
        <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
          <div
            className="h-full rounded-full bg-brand-500 transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Live stream */}
      {(wsStatus === "live" || streamLines.length > 0) && (
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="h-4 w-4 text-brand-500" />
            <h2 className="font-semibold text-gray-800 text-sm">
              Live stream {wsStatus === "live" ? "●" : ""}
            </h2>
          </div>
          <div className="max-h-64 overflow-y-auto rounded-lg bg-gray-900 p-4 font-mono text-xs text-green-400 leading-relaxed">
            {streamLines.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
            <div ref={streamEndRef} />
          </div>
        </div>
      )}

      {/* Rewrites list */}
      {rewrites && rewrites.length > 0 && (
        <div className="card">
          <h2 className="mb-4 font-semibold text-gray-800">Page Rewrites</h2>
          <div className="divide-y divide-gray-50">
            {rewrites.map((rw) => (
              <RewriteRow key={rw.id} rewrite={rw} />
            ))}
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="card w-full max-w-sm space-y-4">
            <h2 className="font-semibold text-gray-900">Delete Job</h2>
            <p className="text-sm text-gray-600">
              This will permanently delete the job, all rewrites, risk findings,
              reviews, and comments. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                className="btn-secondary"
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleteMut.isPending}
              >
                Cancel
              </button>
              <button
                className="btn-primary bg-red-600 hover:bg-red-700"
                onClick={() => deleteMut.mutate()}
                disabled={deleteMut.isPending}
              >
                {deleteMut.isPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RewriteRow({ rewrite }: { rewrite: SectionRewriteOut }) {
  const navigate = useNavigate();
  const hasRisk = rewrite.risk_findings.some(
    (r) => r.severity === "critical" || r.severity === "high"
  );
  
  const isApproved = rewrite.review_status === "approved" || rewrite.review_status === "edited";

  return (
    <div className={`flex items-start gap-4 py-3 px-3 rounded-md text-sm transition-colors ${
      isApproved ? "bg-green-50/50 border border-green-200" : "hover:bg-gray-50"
    }`}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <StatusBadge status={rewrite.status} />
          {hasRisk && <span className="badge badge-red">Risk</span>}
          {isApproved && <span className="badge bg-green-100 text-green-700">Approved</span>}
          <span className="text-xs text-gray-400">
            {rewrite.tokens_completion} tokens · {rewrite.duration_ms}ms
          </span>
        </div>
        {rewrite.rewritten_text && (
          <p className="text-gray-600 line-clamp-2">{rewrite.rewritten_text.slice(0, 200)}</p>
        )}
      </div>
      {rewrite.status === "completed" && (
        <button
          className={`btn-secondary text-xs py-1 shrink-0 ${isApproved ? "!border-green-300 !text-green-700 hover:!bg-green-100" : ""}`}
          onClick={() => navigate(`/reviews/${rewrite.id}`)}
        >
          {isApproved ? "Approved ✓" : "Review"}
        </button>
      )}
    </div>
  );
}
