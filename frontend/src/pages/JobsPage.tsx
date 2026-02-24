import { useMemo, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Briefcase, Play, Eye } from "lucide-react";
import { jobsApi } from "@/api/jobs";
import { documentsApi } from "@/api/documents";
import { rulesetsApi } from "@/api/rulesets";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";
import Spinner from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { extractErrorMessage } from "@/api/client";

export default function JobsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<string>(
    (location.state as { documentId?: string })?.documentId ?? ""
  );
  const [selectedRuleset, setSelectedRuleset] = useState("");

  const { data: jobsData, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => jobsApi.list({ page: 1, page_size: 50 }),
    refetchInterval: (query) =>
      query.state.data?.items.some((j) => j.status === "running") ? 3000 : false,
  });

  const { data: docs } = useQuery({
    queryKey: ["documents", "mapped"],
    queryFn: () => documentsApi.list({ page: 1, page_size: 100, status: "mapped" }),
    enabled: showCreate,
  });

  const { data: rulesets } = useQuery({
    queryKey: ["rulesets", "active"],
    queryFn: () => rulesetsApi.list(),
    enabled: showCreate,
  });

  const activeRulesets = useMemo(
    () => (rulesets ?? []).filter((r) => r.is_active),
    [rulesets]
  );

  const selectedRulesetObj = useMemo(
    () => (rulesets ?? []).find((r) => r.id === selectedRuleset),
    [rulesets, selectedRuleset]
  );

  const createMut = useMutation({
    mutationFn: () => jobsApi.create(selectedDoc, selectedRuleset),
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setShowCreate(false);
      navigate(`/jobs/${job.id}`);
    },
    onError: (err) => setError(extractErrorMessage(err)),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Rewrite Jobs</h1>
          <p className="text-sm text-gray-500">
            Create and monitor LLM rewrite jobs
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
          <Play className="h-4 w-4" />
          New Job
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="card space-y-4">
          <h2 className="font-semibold text-gray-800">Create Rewrite Job</h2>
          {error && (
            <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <div>
            <label className="label">Document (mapped)</label>
            <select
              className="input"
              value={selectedDoc}
              onChange={(e) => setSelectedDoc(e.target.value)}
            >
              <option value="">Select a document…</option>
              {docs?.items.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.original_filename}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Active Ruleset</label>
            <select
              className="input"
              value={selectedRuleset}
              onChange={(e) => setSelectedRuleset(e.target.value)}
            >
              <option value="">Select a ruleset…</option>
              {rulesets?.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} v{r.version} {r.is_active ? "(active)" : "(inactive)"}
                </option>
              ))}
            </select>
            {activeRulesets.length === 0 && (
              <p className="mt-1 text-xs text-amber-700">
                No active rulesets found. Activate one from the Rulesets page before creating a job.
              </p>
            )}
            {selectedRulesetObj && !selectedRulesetObj.is_active && (
              <p className="mt-1 text-xs text-amber-700">
                Selected ruleset is inactive. Activate it first from the Rulesets page.
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button
              className="btn-primary"
              disabled={
                !selectedDoc ||
                !selectedRuleset ||
                !selectedRulesetObj?.is_active ||
                createMut.isPending
              }
              onClick={() => createMut.mutate()}
            >
              {createMut.isPending ? "Creating…" : "Create & Run"}
            </button>
            <button
              className="btn-secondary"
              onClick={() => { setShowCreate(false); setError(null); }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : !jobsData?.items.length ? (
        <EmptyState
          icon={<Briefcase className="h-10 w-10 text-gray-300" />}
          title="No jobs yet"
          description="Create a rewrite job from a mapped document."
        />
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Job ID", "Status", "Sections", "Progress", "Created", ""].map(
                  (h) => (
                    <th key={h} className="px-4 py-3 text-left font-medium text-gray-500">
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {jobsData.items.map((job) => (
                <tr key={job.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-400">
                    {job.id.slice(0, 8)}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {job.total_sections}
                  </td>
                  <td className="px-4 py-3">
                    <ProgressBar
                      value={job.completed_sections}
                      max={job.total_sections}
                    />
                  </td>
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                    {formatDate(job.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      className="btn-ghost p-1"
                      onClick={() => navigate(`/jobs/${job.id}`)}
                    >
                      <Eye className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div
          className="h-full rounded-full bg-brand-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 w-8 text-right">{pct}%</span>
    </div>
  );
}
