import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Play } from "lucide-react";
import { documentsApi } from "@/api/documents";
import StatusBadge from "@/components/ui/StatusBadge";
import Spinner from "@/components/ui/Spinner";
import { formatBytes, formatDate } from "@/lib/utils";
import type { DocumentGraphNode } from "@/types/api";

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: doc, isLoading } = useQuery({
    queryKey: ["documents", id],
    queryFn: () => documentsApi.get(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "extracting" || s === "mapping" ? 2000 : false;
    },
  });

  const { data: graph } = useQuery({
    queryKey: ["documents", id, "graph"],
    queryFn: () => documentsApi.graph(id!),
    enabled: !!id && doc?.status === "mapped",
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );
  }

  if (!doc) return <p className="text-gray-500">Document not found.</p>;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="btn-ghost p-1"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {doc.original_filename}
            </h1>
            <div className="mt-1 flex items-center gap-3 text-sm text-gray-500">
              <span>{doc.mime_type.includes("pdf") ? "PDF" : "DOCX"}</span>
              <span>{formatBytes(doc.file_size_bytes)}</span>
              {doc.page_count && <span>{doc.page_count} pages</span>}
              <span>Uploaded {formatDate(doc.created_at)}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <StatusBadge status={doc.status} />
          {doc.status === "mapped" && (
            <button
              className="btn-primary"
              onClick={() => navigate("/jobs", { state: { documentId: doc.id } })}
            >
              <Play className="h-4 w-4" />
              New Job
            </button>
          )}
        </div>
      </div>

      {/* Error */}
      {doc.error_message && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
          <strong>Ingestion error:</strong> {doc.error_message}
        </div>
      )}

      {/* Document tree */}
      {graph ? (
        <div className="card">
          <h2 className="mb-4 font-semibold text-gray-800">Document Structure</h2>
          <div className="max-h-[60vh] overflow-y-auto">
            <SectionTree node={graph} depth={0} />
          </div>
        </div>
      ) : doc.status === "mapped" ? (
        <div className="flex justify-center py-10"><Spinner /></div>
      ) : (
        <div className="card text-sm text-gray-400 text-center py-10">
          {doc.status === "failed"
            ? "Ingestion failed — see error above."
            : "Document is being processed…"}
        </div>
      )}
    </div>
  );
}

function SectionTree({ node, depth }: { node: DocumentGraphNode; depth: number }) {
  const { section, children } = node;
  const indent = depth * 16;
  return (
    <div>
      <div
        className="flex items-start gap-3 rounded-lg px-3 py-2 hover:bg-gray-50 text-sm"
        style={{ paddingLeft: `${indent + 12}px` }}
      >
        <span className="badge badge-gray mt-0.5 shrink-0 text-xs">
          {section.section_type}
        </span>
        <div className="flex-1 min-w-0">
          {section.heading && (
            <p className="font-medium text-gray-800 truncate">{section.heading}</p>
          )}
          <p className="text-gray-500 line-clamp-2 mt-0.5">
            {section.original_text.slice(0, 150)}
            {section.original_text.length > 150 ? "…" : ""}
          </p>
        </div>
        <span className="text-xs text-gray-300 shrink-0">
          {section.char_count} chars
        </span>
      </div>
      {children.map((child) => (
        <SectionTree key={child.section.id} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}
