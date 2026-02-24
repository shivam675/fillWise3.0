import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center text-center px-4">
      <p className="text-6xl font-bold text-brand-600">404</p>
      <h1 className="mt-4 text-xl font-semibold text-gray-900">
        Page not found
      </h1>
      <p className="mt-2 text-sm text-gray-500">
        The page you are looking for doesn't exist or has been moved.
      </p>
      <Link to="/documents" className="btn-primary mt-6">
        Back to Documents
      </Link>
    </div>
  );
}
