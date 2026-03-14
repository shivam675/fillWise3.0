import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Upload, CheckCircle, Plus, Download, Edit2, Trash2 } from "lucide-react";
import { rulesetsApi } from "@/api/rulesets";
import EmptyState from "@/components/ui/EmptyState";
import Spinner from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { extractErrorMessage } from "@/api/client";
import { RulesetOut } from "@/types/api";

export default function RulesetsPage() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editJson, setEditJson] = useState<string>("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

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

  const deleteMut = useMutation({
    mutationFn: (id: string) => rulesetsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rulesets"] });
      setDeleteConfirmId(null);
      setError(null);
    },
    onError: (err) => setError(extractErrorMessage(err)),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string, data: any }) => rulesetsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rulesets"] });
      setEditingId(null);
      setError(null);
    },
    onError: (err) => setError(extractErrorMessage(err)),
  });

  const handleEditClick = (rs: RulesetOut) => {
    setEditingId(rs.id);
    const { id, content_hash, is_active, created_by, created_at, updated_at, schema_version, ...editable } = rs as any;
    setEditJson(JSON.stringify(editable, null, 2));
  };

  const activateMut = useMutation({
    mutationFn: (id: string) => rulesetsApi.activate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rulesets"] }),
    onError: (err) => setError(extractErrorMessage(err)),
  });

  const deactivateMut = useMutation({
    mutationFn: (id: string) => rulesetsApi.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rulesets"] }),
    onError: (err) => setError(extractErrorMessage(err)),
  });

  const handleDownload = (rs: RulesetOut) => {
    const exportData = {
      name: rs.name,
      description: rs.description,
      version: rs.version,
      jurisdiction: rs.jurisdiction,
      rules: rs.rules.map(r => ({
        id: r.id,
        name: r.name,
        instruction: r.instruction
      }))
    };
    
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportData, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", `${rs.name.replace(/\s+/g, "_").toLowerCase()}_v${rs.version}.json`);
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Rulesets</h1>
          <p className="text-sm text-gray-500">
            Create or upload YAML/JSON rule files and activate them for rewrite jobs   
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/rulesets/new"
            className="btn-secondary"
          >
            <Plus className="h-4 w-4 mr-1" />
            Create Manually
          </Link>
          <button
            className="btn-primary"
            onClick={() => inputRef.current?.click()}
            disabled={uploadMut.isPending}
          >
            <Upload className="h-4 w-4 mr-1" />
            Upload Rule File
          </button>
        </div>
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
              {editingId === rs.id ? (
                <div className="space-y-3">
                  <h3 className="font-semibold text-gray-900">Edit Ruleset</h3>
                  <textarea 
                    className="w-full h-64 p-2 text-sm font-mono border rounded-md focus:ring-2 focus:ring-blue-500 outline-none"
                    value={editJson}
                    onChange={e => setEditJson(e.target.value)}
                  />
                  <div className="flex gap-2 justify-end">
                    <button className="btn-ghost text-sm py-1" onClick={() => setEditingId(null)}>Cancel</button>
                    <button 
                      className="btn-primary text-sm py-1" 
                      onClick={() => {
                        try {
                          const parsed = JSON.parse(editJson);
                          updateMut.mutate({ id: rs.id, data: parsed });
                        } catch (e) {
                          setError("Invalid JSON format");
                        }
                      }}
                      disabled={updateMut.isPending}
                    >
                      Save Changes
                    </button>
                  </div>
                </div>
              ) : (
                <>
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
                  {deleteConfirmId === rs.id ? (
                    <div className="flex items-center gap-1 bg-red-50 p-1 rounded">
                      <span className="text-xs text-red-600 mr-1 font-semibold">Delete?</span>
                      <button className="btn-secondary text-xs py-1 px-2 border-red-200 text-red-600 hover:bg-red-100" onClick={() => setDeleteConfirmId(null)}>No</button>
                      <button className="btn-primary text-xs py-1 px-2 bg-red-600 border-red-600 hover:bg-red-700 focus:ring-red-500" onClick={() => deleteMut.mutate(rs.id)}>Yes</button>
                    </div>
                  ) : (
                    <>
                      <button
                        className="btn-ghost text-xs py-1 px-2 text-gray-500 hover:text-blue-600"
                        onClick={() => handleEditClick(rs)}
                        title="Edit Ruleset"
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                      <button
                        className="btn-ghost text-xs py-1 px-2 text-gray-500 hover:text-red-600"
                        onClick={() => setDeleteConfirmId(rs.id)}
                        title="Delete Ruleset"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </>
                  )}
                  <button
                    className="btn-secondary text-xs py-1"
                    onClick={() => handleDownload(rs)}
                    title="Download as JSON"
                  >
                    <Download className="h-3 w-3 mr-1" /> Download
                  </button>
                  {rs.is_active ? (
                    <button
                      className="btn-secondary text-xs py-1 text-red-600 hover:text-red-700"
                      onClick={() => deactivateMut.mutate(rs.id)}
                      disabled={deactivateMut.isPending}
                    >
                      Deactivate
                    </button>
                  ) : (
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
                        {rule.priority !== undefined && (
                          <span className="text-xs text-gray-400">
                            priority {rule.priority}
                          </span>
                        )}
                        {(rule.section_types || []).map((t) => (
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
              </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
