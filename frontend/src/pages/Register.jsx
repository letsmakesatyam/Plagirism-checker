import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { apiErrorMessage } from "../api/client";
import ErrorBanner from "../components/ErrorBanner";
import { AuthShell } from "./Login";

export default function Register() {
  const { register: registerUser } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const { register, handleSubmit, control, formState: { errors, isSubmitting } } = useForm({
    defaultValues: { role: "student" },
  });
  const role = useWatch({ control, name: "role" });

  const onSubmit = async (values) => {
    setError(null);
    try {
      const user = await registerUser(values);
      navigate(user.role === "faculty" ? "/faculty/dashboard" : "/student/dashboard", { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err, "Could not create your account."));
    }
  };

  return (
    <AuthShell
      eyebrow="Get started"
      title="Create your account"
      footer={
        <>
          Already registered?{" "}
          <Link to="/login" className="text-forest font-medium hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <ErrorBanner message={error} />

        <div>
          <label className="label">I am a</label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className={`btn-secondary cursor-pointer ${role === "student" ? "bg-forest text-paper" : ""}`}>
              <input type="radio" value="student" className="hidden" {...register("role")} />
              Student
            </label>
            <label className={`btn-secondary cursor-pointer ${role === "faculty" ? "bg-forest text-paper" : ""}`}>
              <input type="radio" value="faculty" className="hidden" {...register("role")} />
              Faculty
            </label>
          </div>
        </div>

        <div>
          <label className="label">Full name</label>
          <input className="input" placeholder="Jane Doe" {...register("full_name", { required: "Full name is required", minLength: { value: 2, message: "Too short" } })} />
          {errors.full_name && <p className="text-xs text-rust mt-1">{errors.full_name.message}</p>}
        </div>

        <div>
          <label className="label">Email</label>
          <input type="email" className="input" placeholder="you@college.edu" {...register("email", { required: "Email is required" })} />
          {errors.email && <p className="text-xs text-rust mt-1">{errors.email.message}</p>}
        </div>

        <div>
          <label className="label">Password</label>
          <input type="password" className="input" placeholder="At least 8 characters" {...register("password", { required: "Password is required", minLength: { value: 8, message: "Must be at least 8 characters" } })} />
          {errors.password && <p className="text-xs text-rust mt-1">{errors.password.message}</p>}
        </div>

        {role === "student" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="label">Roll number</label>
              <input className="input" {...register("roll_number")} />
            </div>
            <div>
              <label className="label">Division / Batch</label>
              <input className="input" placeholder="A / Batch 1" {...register("division")} />
            </div>
          </div>
        ) : (
          <div>
            <label className="label">Department</label>
            <input className="input" placeholder="Computer Engineering" {...register("department")} />
          </div>
        )}

        <button type="submit" className="btn-primary w-full" disabled={isSubmitting}>
          {isSubmitting ? "Creating account…" : "Create account"}
        </button>
      </form>
    </AuthShell>
  );
}
