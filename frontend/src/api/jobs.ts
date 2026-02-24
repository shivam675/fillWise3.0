import { http } from "./client";
import type { RewriteJobOut, SectionRewriteOut } from "@/types/api";

export const jobsApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    http
      .get<{ items: RewriteJobOut[]; total: number }>("/jobs", { params })
      .then((r) => r.data),

  get: (id: string) =>
    http.get<RewriteJobOut>(`/jobs/${id}`).then((r) => r.data),

  create: (documentId: string, rulesetId: string) =>
    http
      .post<RewriteJobOut>("/jobs", {
        document_id: documentId,
        ruleset_id: rulesetId,
      })
      .then((r) => r.data),

  rewrites: (id: string) =>
    http
      .get<SectionRewriteOut[]>(`/jobs/${id}/rewrites`)
      .then((r) => r.data),

  assemble: (id: string) =>
    http.post(`/jobs/${id}/assemble`).then((r) => r.data),

  /** Download the assembled DOCX export. Uses blob response type for file download. */
  downloadExport: (documentId: string, jobId: string) =>
    http
      .get(`/documents/${documentId}/export`, {
        params: { job_id: jobId },
        responseType: "blob",
      })
      .then((r) => {
        const url = window.URL.createObjectURL(r.data as Blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `fillwise_export_${jobId.slice(0, 8)}.docx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }),
};
