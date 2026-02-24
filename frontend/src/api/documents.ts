import { http } from "./client";
import type {
  DocumentListResponse,
  DocumentOut,
  SectionOut,
  DocumentGraphNode,
} from "@/types/api";

export const documentsApi = {
  list: (params?: { page?: number; page_size?: number; status?: string }) =>
    http
      .get<DocumentListResponse>("/documents", { params })
      .then((r) => r.data),

  get: (id: string) =>
    http.get<DocumentOut>(`/documents/${id}`).then((r) => r.data),

  upload: (file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    form.append("file", file);
    return http
      .post<DocumentOut>("/documents", form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: onProgress
          ? (e) => {
              if (e.total) onProgress(Math.round((e.loaded * 100) / e.total));
            }
          : undefined,
      })
      .then((r) => r.data);
  },

  delete: (id: string) =>
    http.delete(`/documents/${id}`).then((r) => r.data),

  sections: (id: string) =>
    http.get<SectionOut[]>(`/documents/${id}/sections`).then((r) => r.data),

  graph: (id: string) =>
    http
      .get<DocumentGraphNode>(`/documents/${id}/graph`)
      .then((r) => r.data),

  exportUrl: (documentId: string, jobId: string) =>
    `/api/v1/documents/${documentId}/export?job_id=${jobId}`,
};
