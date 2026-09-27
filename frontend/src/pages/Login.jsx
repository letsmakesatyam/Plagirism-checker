import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { apiErrorMessage } from "../api/client";
import ErrorBanner from "../components/ErrorBanner";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm();

  const onSubmit = async (values) => {
    setError(null);
    try {
      const user = await login(values.email, values.password);
      const dest = location.state?.from || (user.role === "faculty" ? "/faculty/dashboard" : "/student/dashboard");
      navigate(dest, { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err, "Could not sign in. Check your email and password."));
    }
  };

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in to Originum"
      footer={
        <>
          New here?{" "}
          <Link to="/register" className="text-forest font-medium hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <ErrorBanner message={error} />
        <div>
          <label className="label">Email</label>
          <input
            type="email"
            className="input"
            placeholder="you@college.edu"
            {...register("email", { required: "Email is required" })}
          />
          {errors.email && <p className="text-xs text-rust mt-1">{errors.email.message}</p>}
        </div>
        <div>
          <label className="label">Password</label>
          <input
            type="password"
            className="input"
            placeholder="••••••••"
            {...register("password", { required: "Password is required" })}
          />
          {errors.password && <p className="text-xs text-rust mt-1">{errors.password.message}</p>}
        </div>
        <button type="submit" className="btn-primary w-full" disabled={isSubmitting}>
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthShell>
  );
}

export function AuthShell({ eyebrow, title, children, footer }) {
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <span className="mx-auto mb-4 h-12 w-12 rounded-seal border-2 border-brass flex items-center justify-center font-display text-brass text-xl">
            O
          </span>
          <p className="eyebrow">{eyebrow}</p>
          <h1 className="font-display text-2xl text-ink mt-1">{title}</h1>
        </div>
        <div className="card">{children}</div>
        {footer && <p className="text-center text-sm text-slate mt-6">{footer}</p>}
      </div>
    </div>
  );
}
