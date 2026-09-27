import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center flex-col gap-3 text-center px-4">
      <p className="eyebrow">404</p>
      <h1 className="font-display text-3xl">This page isn't on file</h1>
      <p className="text-slate max-w-sm">The page you're looking for doesn't exist or may have moved.</p>
      <Link to="/" className="btn-primary mt-3">Back to dashboard</Link>
    </div>
  );
}
