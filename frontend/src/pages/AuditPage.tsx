import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, ShieldCheck, ShieldAlert } from "lucide-react";
import { auditApi } from "@/api/audit";
import Spinner from "@/components/ui/Spinner";
import EmptyState from "@/components/ui/EmptyState";
import { formatDate } from "@/lib/utils";

export default function AuditPage() {
  const [page, setPage] = useState(1);
  const [eventTypeFilter, setEventTypeFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["audit", page, eventTypeFilter],
    queryFn: () =>
      auditApi.list({
        page,
        page_size: 50,
        event_type: eventTypeFilter || undefined,
      }),
  });

  const { data: chainResult } = useQuery({
    queryKey: ["audit", "verify"],
    queryFn: () => auditApi.verify(),
    staleTime: 60_000,
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Audit Log</h1>
          <p className="text-sm text-gray-500">
            Immutable hash-chained event log
          </p>
        </div>
      </div>

      {/* Chain integrity banner */}
      {chainResult && (
        <div
          className={`rounded-lg p-4 flex items-start gap-3 text-sm ${
            chainResult.valid
              ? "bg-green-50 text-green-800"
              : "bg-red-50 text-red-800"
          }`}
        >
          {chainResult.valid ? (
            <ShieldCheck className="h-5 w-5 mt-0.5 shrink-0" />
          ) : (
            <ShieldAlert className="h-5 w-5 mt-0.5 shrink-0" />
          )}
          <div>
            <p className="font-medium">
              {chainResult.valid
                ? "Hash chain intact"
                : "Hash chain integrity violation detected"}
            </p>
            <p className="mt-0.5 text-xs">{chainResult.message}</p>
            {!chainResult.valid && chainResult.first_broken_at && (
              <p className="mt-0.5 text-xs">
                First broken event: {chainResult.first_broken_at}
              </p>
            )}
            <p className="mt-0.5 text-xs">
              {chainResult.total_events} events verified
            </p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2">
        <input
          className="input max-w-xs"
          placeholder="Filter by event type…"
          value={eventTypeFilter}
          onChange={(e) => { setEventTypeFilter(e.target.value); setPage(1); }}
        />
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : !data?.items.length ? (
        <EmptyState
          icon={<ClipboardList className="h-10 w-10 text-gray-300" />}
          title="No audit events"
          description="Events are recorded automatically as the system operates."
        />
      ) : (
        <>
          <div className="card p-0 overflow-auto">
            <table className="min-w-full divide-y divide-gray-100 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {["Time", "Event", "Actor", "Entity", "Hash"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left font-medium text-gray-500 whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {data.items.map((ev) => (
                  <tr key={ev.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap text-xs">
                      {formatDate(ev.created_at)}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-800">
                      {ev.event_type}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {ev.actor_username ?? ev.actor_id?.slice(0, 8) ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {ev.entity_type
                        ? `${ev.entity_type}:${ev.entity_id?.slice(0, 8)}`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-300">
                      {ev.event_hash.slice(0, 12)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              {(page - 1) * 50 + 1}–{Math.min(page * 50, data.total)} of{" "}
              {data.total} events
            </span>
            <div className="flex gap-2">
              <button
                className="btn-secondary py-1 text-xs"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </button>
              <button
                className="btn-secondary py-1 text-xs"
                disabled={page * 50 >= data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
