import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import * as dashboardApi from "../../api/dashboard";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import StatusBadge from "../../components/StatusBadge";
import { apiErrorMessage } from "../../api/client";

export default function StudentDashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["student-dashboard"],
    queryFn: dashboardApi.studentDashboard,
  });

  if (isLoading) return <Spinner label="Loading your dashboard" />;
  if (error) return <ErrorBanner message={apiErrorMessage(error, "Could not load the dashboard.")} />;

  return (
    <div className="space-y-10">
      <header>
        <p className="eyebrow">Student overview</p>
        <h1 className="font-display text-3xl text-ink mt-1">Your dashboard</h1>
      </header>

      <section className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Available assignments" value={data.total_assignments_available} />
        <StatCard label="Your submissions" value={data.total_submissions} />
        <StatCard label="Pending assignments" value={data.pending_assignments?.length ?? 0} />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="font-display text-lg mb-4">Pending assignments</h2>
          {data.pending_assignments?.length ? (
            <ul className="divide-y divide-line">
              {data.pending_assignments.map((a) => (
                <li key={a.assignment_id} className="py-3 flex items-center justify-between">
                  <span className="text-sm font-medium text-ink">{a.title}</span>
                  {a.due_date && <span className="text-xs font-mono text-slate-light">due {new Date(a.due_date).toLocaleDateString()}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Nothing pending" description="You're caught up — no active assignments waiting for a submission." />
          )}
          <Link to="/student/assignments" className="btn-secondary mt-4 w-full justify-center">Browse assignments</Link>
        </div>

        <div className="card">
          <h2 className="font-display text-lg mb-4">Recent submissions</h2>
          {data.recent_submissions?.length ? (
            <ul className="divide-y divide-line">
              {data.recent_submissions.map((s) => (
                <li key={s.submission_id} className="py-3">
                  <div className="flex items-center justify-between gap-3">
                    <Link to={`/submissions/${s.submission_id}`} className="text-sm font-medium text-ink hover:text-forest truncate">
                      {s.original_filename}
                    </Link>
                    <StatusBadge status={s.status} />
                  </div>
                  <p className="text-xs text-slate-light mt-0.5">{s.assignment_title}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No submissions yet" description="Upload your first assignment to see it here." />
          )}
        </div>
      </section>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="card">
      <p className="text-xs uppercase tracking-wide text-slate mb-1">{label}</p>
      <p className="font-display text-3xl text-ink">{value}</p>
    </div>
  );
}
