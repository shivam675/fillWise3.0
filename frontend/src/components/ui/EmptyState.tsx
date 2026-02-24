import type { ReactNode } from "react";

interface Props {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export default function EmptyState({ icon, title, description, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-200 bg-white py-16 text-center">
      {icon && <div className="mb-3">{icon}</div>}
      <p className="font-medium text-gray-700">{title}</p>
      {description && (
        <p className="mt-1 text-sm text-gray-400">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
