import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Users, UserPlus, Trash2 } from "lucide-react";
import { adminApi } from "@/api/admin";
import EmptyState from "@/components/ui/EmptyState";
import Spinner from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { extractErrorMessage } from "@/api/client";
import type { RoleEnum } from "@/types/api";
import { useAuthStore } from "@/stores/auth";

interface CreateForm {
  username: string;
  password: string;
  email: string;
  role: RoleEnum;
}

export default function AdminPage() {
  const qc = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const { data: users, isLoading } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => adminApi.listUsers(),
  });

  const createMut = useMutation({
    mutationFn: (data: CreateForm) =>
      adminApi.createUser({ ...data, email: data.email || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      setShowCreate(false);
      setError(null);
      reset();
    },
    onError: (err) => setError(extractErrorMessage(err)),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => adminApi.deleteUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
    onError: (err) => setError(extractErrorMessage(err)),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateForm>({ defaultValues: { role: "VIEWER" } });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">User Management</h1>
          <p className="text-sm text-gray-500">Create and manage system users</p>
        </div>
        <button
          className="btn-primary"
          onClick={() => setShowCreate(!showCreate)}
        >
          <UserPlus className="h-4 w-4" />
          New User
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {/* Create form */}
      {showCreate && (
        <div className="card space-y-4">
          <h2 className="font-semibold text-gray-800">Create User</h2>
          <form
            onSubmit={handleSubmit((data) => createMut.mutate(data))}
            className="grid grid-cols-2 gap-4"
          >
            <div>
              <label className="label">Username *</label>
              <input
                className="input"
                {...register("username", { required: true })}
              />
              {errors.username && (
                <p className="text-xs text-red-600 mt-1">Required</p>
              )}
            </div>
            <div>
              <label className="label">Password *</label>
              <input
                type="password"
                className="input"
                {...register("password", { required: true, minLength: 12 })}
              />
              {errors.password && (
                <p className="text-xs text-red-600 mt-1">
                  Min 12 characters required
                </p>
              )}
            </div>
            <div>
              <label className="label">Email</label>
              <input type="email" className="input" {...register("email")} />
            </div>
            <div>
              <label className="label">Role *</label>
              <select className="input" {...register("role", { required: true })}>
                {(["ADMIN", "EDITOR", "REVIEWER", "VIEWER"] as RoleEnum[]).map(
                  (r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  )
                )}
              </select>
            </div>
            <div className="col-span-2 flex gap-2">
              <button
                type="submit"
                className="btn-primary"
                disabled={createMut.isPending}
              >
                {createMut.isPending ? "Creating…" : "Create"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => { setShowCreate(false); setError(null); reset(); }}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Users table */}
      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner /></div>
      ) : !users?.length ? (
        <EmptyState
          icon={<Users className="h-10 w-10 text-gray-300" />}
          title="No users"
          description="Create the first user above."
        />
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {["Username", "Email", "Role", "Status", "Created", ""].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left font-medium text-gray-500"
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {user.username}
                    {user.id === currentUser?.id && (
                      <span className="ml-2 badge badge-blue text-xs">You</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{user.email ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className="badge badge-purple">{user.role}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={
                        user.is_active ? "badge-green" : "badge-gray"
                      }
                    >
                      {user.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                    {formatDate(user.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      className="btn-ghost p-1 text-red-400 hover:bg-red-50 disabled:opacity-30"
                      disabled={user.id === currentUser?.id}
                      title="Delete user"
                      onClick={() => {
                        if (confirm(`Delete user "${user.username}"?`))
                          deleteMut.mutate(user.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
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
