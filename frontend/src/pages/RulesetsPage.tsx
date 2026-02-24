import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Upload, CheckCircle } from "lucide-react";
import { rulesetsApi } from "@/api/rulesets";
import EmptyState from "@/components/ui/EmptyState";
import Spinner from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { extractErrorMessage } from "@/api/client";

export default function RulesetsPage() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: rulesets, isLoading } = useQuery({
    queryKey: ["rulesets"],
    queryFn: () => rulesetsApi.list(),
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => rulesetsApi.create(file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rulesets"] });
      setError(null);
    },
    onError: (err) => setError(extractErrorMessage(err)),
  });

  const activateMut = useMutation({
    mutationFn: (id: string) => rulesetsApi.activate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rulesets"] }),
    onError: (err) => setError(extractErrorMessage(err)),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Rulesets</h1>
          <p className="text-sm text-gray-500">
            Upload YAML or JSON rule files and activate them for rewrite jobs
          </p>
        </div>
        <button
          className="btn-primary"
          onClick={() => inputRef.current?.click()}
          disabled={uploadMut.isPending}
        >
          <Upload className="h-4 w-4" />
          Upload Rule File
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".yaml,.yml,.json"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) { setError(null); uploadMut.mutate(f); }
            e.target.value = "";
          }}
        />
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : !rulesets?.length ? (
        <EmptyState
          icon={<BookOpen className="h-10 w-10 text-gray-300" />}
          title="No rulesets yet"
          description="Upload a YAML ruleset to get started. See rules/samples/ for examples."
        />
      ) : (
        <div className="space-y-3">
          {rulesets.map((rs) => (
            <div key={rs.id} className="card">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-semibold text-gray-900">{rs.name}</h3>
                    <span className="text-xs text-gray-400">v{rs.version}</span>
                    {rs.jurisdiction && (
                      <span className="badge badge-gray">{rs.jurisdiction}</span>
                    )}
                    {rs.is_active && (
                      <span className="badge badge-green">
                        <CheckCircle className="mr-1 h-3 w-3" /> Active
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-gray-500 line-clamp-2">
                    {rs.description}
                  </p>
                  <p className="mt-1 text-xs text-gray-400">
                    {rs.rules.length} rules · Created {formatDate(rs.created_at)}
                  </p>
                </div>

                <div className="flex items-center gap-2 ml-4 shrink-0">
                  {!rs.is_active && (
                    <button
                      className="btn-secondary text-xs py-1"
                      onClick={() => activateMut.mutate(rs.id)}
                      disabled={activateMut.isPending}
                    >
                      Activate
                    </button>
                  )}
                  <button
                    className="btn-ghost text-xs py-1"
                    onClick={() =>
                      setExpanded(expanded === rs.id ? null : rs.id)
                    }
                  >
                    {expanded === rs.id ? "Hide rules" : "View rules"}
                  </button>
                </div>
              </div>

              {expanded === rs.id && (
                <div className="mt-4 space-y-2">
                  {rs.rules.map((rule) => (
                    <div
                      key={rule.id}
                      className="rounded-lg border border-gray-100 bg-gray-50 p-3 text-sm"
                    >
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-mono text-xs text-gray-400">
                          {rule.id}
                        </span>
                        <span className="font-medium text-gray-800">
                          {rule.name}
                        </span>
                        <span className="text-xs text-gray-400">
                          priority {rule.priority}
                        </span>
                        {rule.section_types.map((t) => (
                          <span key={t} className="badge badge-gray text-xs">
                            {t}
                          </span>
                        ))}
                      </div>
                      <p className="text-gray-600 whitespace-pre-wrap text-xs leading-relaxed">
                        {rule.instruction}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
