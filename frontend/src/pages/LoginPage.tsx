import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { Scale, AlertCircle } from "lucide-react";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { extractErrorMessage } from "@/api/client";

interface FormValues {
  username: string;
  password: string;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuthStore();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>();

  const onSubmit = async ({ username, password }: FormValues) => {
    setServerError(null);
    try {
      const tokens = await authApi.login(username, password);
      setTokens(tokens.access_token, tokens.refresh_token);
      const user = await authApi.me();
      setUser(user);
      navigate("/documents", { replace: true });
    } catch (err) {
      setServerError(extractErrorMessage(err));
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="mb-8 flex flex-col items-center gap-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-white">
            <Scale className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">FillWise</h1>
          <p className="text-sm text-gray-500">Legal document transformation</p>
        </div>

        {/* Card */}
        <div className="card">
          <h2 className="mb-5 text-lg font-semibold text-gray-800">Sign in</h2>

          {serverError && (
            <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="label" htmlFor="username">
                Username
              </label>
              <input
                id="username"
                autoComplete="username"
                className="input"
                {...register("username", { required: "Username is required" })}
              />
              {errors.username && (
                <p className="mt-1 text-xs text-red-600">
                  {errors.username.message}
                </p>
              )}
            </div>

            <div>
              <label className="label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="input"
                {...register("password", { required: "Password is required" })}
              />
              {errors.password && (
                <p className="mt-1 text-xs text-red-600">
                  {errors.password.message}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-primary w-full justify-center py-2.5"
            >
              {isSubmitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
