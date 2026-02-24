import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";
import type { RoleEnum } from "@/types/api";

interface Props {
  roles: RoleEnum[];
}

export default function RoleRoute({ roles }: Props) {
  const user = useAuthStore((s) => s.user);
  if (!user || !roles.includes(user.role)) {
    return <Navigate to="/documents" replace />;
  }
  return <Outlet />;
}
