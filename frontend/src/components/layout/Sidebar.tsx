import { NavLink } from "react-router-dom";
import {
  FileText,
  BookOpen,
  Briefcase,
  ClipboardList,
  Users,
  Scale,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/rulesets", label: "Rulesets", icon: BookOpen },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
];

const adminItems = [
  { to: "/audit", label: "Audit Log", icon: ClipboardList },
  { to: "/admin/users", label: "Users", icon: Users },
];

export default function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "ADMIN";

  return (
    <aside className="flex w-56 flex-col border-r border-gray-200 bg-white px-3 py-5 shrink-0">
      {/* Brand */}
      <div className="mb-6 flex items-center gap-2 px-2">
        <Scale className="h-6 w-6 text-brand-600" />
        <span className="text-lg font-semibold text-gray-900">FillWise</span>
      </div>

      {/* Main nav */}
      <nav className="flex flex-col gap-0.5">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Admin section */}
      {isAdmin && (
        <>
          <div className="my-3 border-t border-gray-100" />
          <p className="mb-1 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400">
            Admin
          </p>
          <nav className="flex flex-col gap-0.5">
            {adminItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-brand-50 text-brand-700"
                      : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </NavLink>
            ))}
          </nav>
        </>
      )}

      {/* User info at bottom */}
      {user && (
        <div className="mt-auto px-2 pt-4 border-t border-gray-100">
          <p className="text-xs text-gray-500 truncate">{user.username}</p>
          <p className="text-xs text-gray-400">{user.role}</p>
        </div>
      )}
    </aside>
  );
}
