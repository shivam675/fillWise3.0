import { cn } from "@/lib/utils";

interface Props {
  status: string;
  className?: string;
}

const palette: Record<string, string> = {
  // General
  pending:     "badge-gray",
  running:     "badge-blue",
  completed:   "badge-green",
  failed:      "badge-red",
  cancelled:   "badge-gray",
  // Document
  extracting:  "badge-blue",
  extracted:   "badge-blue",
  mapping:     "badge-yellow",
  mapped:      "badge-green",
  // Review
  approved:    "badge-green",
  rejected:    "badge-red",
  edited:      "badge-purple",
  rerun_requested: "badge-yellow",
  // Risk (backend returns lowercase)
  critical:    "badge-red",
  high:        "badge-red",
  medium:      "badge-yellow",
  low:         "badge-blue",
  info:        "badge-gray",
  CRITICAL:    "badge-red",
  HIGH:        "badge-red",
  MEDIUM:      "badge-yellow",
  LOW:         "badge-blue",
  INFO:        "badge-gray",
  // Rewrite
  skipped:     "badge-gray",
};

export default function StatusBadge({ status, className }: Props) {
  const cls = palette[status] ?? "badge-gray";
  return <span className={cn(cls, className)}>{status}</span>;
}
