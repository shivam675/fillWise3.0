import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, Trash2, Eye, RefreshCw } from "lucide-react";
import { documentsApi } from "@/api/documents";
import { formatBytes, formatDate } from "@/lib/utils";
import type { DocumentStatus } from "@/types/api";
import { extractErrorMessage } from "@/api/client";
import EmptyState from "@/components/ui/EmptyState";
import Spinner from "@/components/ui/Spinner";

const STATUS_POLL_INTERVAL_MS = 3000;

export default function DocumentsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: () => documentsApi.list({ page: 1, page_size: 50 }),
    refetchInterval: (query) => {
      const hasProcessing = query.state.data?.items.some(
        (d) => d.status === "extracting" || d.status === "mapping"
      );
      return hasProcessing ? STATUS_POLL_INTERVAL_MS : false;
    },
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) =>
      documentsApi.upload(file, setUploadProgress),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      setUploadProgress(null);
      setUploadError(null);
    },
    onError: (err) => {
      setUploadError(extractErrorMessage(err));
      setUploadProgress(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    uploadMut.mutate(file);
    e.target.value = "";
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Documents</h1>
          <p className="text-sm text-gray-500">
            Upload PDF or DOCX contracts for transformation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary"
            onClick={() => qc.invalidateQueries({ queryKey: ["documents"] })}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
          <button
            className="btn-primary"
            onClick={() => inputRef.current?.click()}
            disabled={uploadMut.isPending}
          >
            <Upload className="h-4 w-4" />
            {uploadMut.isPending ? `Uploading ${uploadProgress ?? 0}%` : "Upload"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      </div>

      {uploadError && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {uploadError}
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<FileText className="h-10 w-10 text-gray-300" />}
          title="No documents yet"
          description="Upload a PDF or DOCX contract to get started."
        />
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Filename", "Type", "Size", "Pages", "Status", "Uploaded", ""].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left font-medium text-gray-500 whitespace-nowrap"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {data.items.map((doc) => (
                <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900 max-w-xs truncate">
                    {doc.original_filename}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {doc.mime_type.includes("pdf") ? "PDF" : "DOCX"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {formatBytes(doc.file_size_bytes)}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {doc.page_count ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <DocumentStatusBadge status={doc.status} />
                  </td>
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                    {formatDate(doc.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        className="btn-ghost p-1"
                        title="View"
                        onClick={() => navigate(`/documents/${doc.id}`)}
                      >
                        <Eye className="h-4 w-4" />
                      </button>
                      <button
                        className="btn-ghost p-1 text-red-500 hover:bg-red-50"
                        title="Delete"
                        onClick={() => {
                          if (confirm("Delete this document?"))
                            deleteMut.mutate(doc.id);
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
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

function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const map: Record<DocumentStatus, string> = {
    pending: "badge-gray",
    extracting: "badge-blue",
    extracted: "badge-blue",
    mapping: "badge-yellow",
    mapped: "badge-green",
    failed: "badge-red",
  };
  return <span className={map[status]}>{status}</span>;
}
