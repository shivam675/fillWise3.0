import { LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";

export default function TopBar() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6 shrink-0">
      <div />
      <div className="flex items-center gap-3">
        {user && (
          <span className="text-sm text-gray-600">
            {user.username}
            <span className="ml-2 badge badge-blue">{user.role}</span>
          </span>
        )}
        <button onClick={handleLogout} className="btn-ghost py-1 px-2" title="Log out">
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
