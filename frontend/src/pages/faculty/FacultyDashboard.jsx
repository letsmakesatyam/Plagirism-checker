import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import * as dashboardApi from "../../api/dashboard";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import ScoreSeal from "../../components/ScoreSeal";
import { apiErrorMessage } from "../../api/client";

const STATUS_COLORS = {
  uploaded: "#8A9793",
  extracting: "#D9AE6B",
  extracted: "#D9AE6B",
  embedding: "#D9AE6B",
  embedded: "#1F4B3F",
  failed: "#B23A2E",
};

export default function FacultyDashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["faculty-dashboard"],
    queryFn: dashboardApi.facultyDashboard,
  });

  if (isLoading) return <Spinner label="Loading your dashboard" />;
  if (error) return <ErrorBanner message={apiErrorMessage(error, "Could not load the dashboard.")} />;

  const statusData = Object.entries(data.submissions_by_status || {}).map(([name, value]) => ({ name, value }));
  const analyticsData = (data.assignment_analytics || []).map((a) => ({
    name: a.title.length > 16 ? a.title.slice(0, 16) + "…" : a.title,
    score: a.average_originality_score ?? 0,
  }));

  return (
    <div className="space-y-10">
      <header>
        <p className="eyebrow">Faculty overview</p>
        <h1 className="font-display text-3xl text-ink mt-1">Your dashboard</h1>
      </header>

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Assignments" value={data.total_assignments} />
        <StatCard label="Submissions" value={data.total_submissions} />
        <StatCard label="Flagged in top plagiarism" value={data.top_plagiarism?.length ?? 0} />
        <StatCard label="Sources indexed" value={data.most_copied_sources?.length ?? 0} />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="font-display text-lg mb-4">Submissions by status</h2>
          {statusData.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={2}>
                  {statusData.map((entry) => (
                    <Cell key={entry.name} fill={STATUS_COLORS[entry.name] || "#8A9793"} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-slate py-16 text-center">No submissions yet.</p>
          )}
        </div>

        <div className="card">
          <h2 className="font-display text-lg mb-4">Average originality by assignment</h2>
          {analyticsData.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={analyticsData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#DBDED4" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="score" fill="#1F4B3F" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-slate py-16 text-center">No reports generated yet.</p>
          )}
        </div>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="font-display text-lg mb-4">Top plagiarism concerns</h2>
          {data.top_plagiarism?.length ? (
            <ul className="divide-y divide-line">
              {data.top_plagiarism.map((entry) => (
                <li key={entry.submission_id} className="py-3 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <Link to={`/submissions/${entry.submission_id}`} className="text-sm font-medium text-ink hover:text-forest truncate block">
                      {entry.original_filename}
                    </Link>
                    <p className="text-xs text-slate-light truncate">{entry.student_name} · {entry.assignment_title}</p>
                  </div>
                  <ScoreSeal value={entry.overall_originality_score} size={48} />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No reports yet" description="Once students submit and you generate reports, the lowest-originality submissions appear here." />
          )}
        </div>

        <div className="card">
          <h2 className="font-display text-lg mb-4">Most-copied internet sources</h2>
          {data.most_copied_sources?.length ? (
            <ul className="divide-y divide-line">
              {data.most_copied_sources.map((s) => (
                <li key={s.matched_source_id} className="py-3 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-ink">{s.title}</p>
                    <p className="text-xs text-slate-light capitalize">{s.category.replace("_", " ")}</p>
                  </div>
                  <span className="font-mono text-sm text-brass">{s.times_matched}×</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No matches yet" description="Source matches will show up here once internet-plagiarism checks find hits in your indexed corpus." />
          )}
        </div>
      </section>

      <section className="card">
        <h2 className="font-display text-lg mb-4">Recent submissions</h2>
        {data.recent_submissions?.length ? (
          <div className="overflow-x-auto -mx-5 px-5 sm:mx-0 sm:px-0">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-light border-b border-line">
                <th className="pb-2 font-medium">File</th>
                <th className="pb-2 font-medium">Student</th>
                <th className="pb-2 font-medium">Assignment</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium">Originality</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.recent_submissions.map((s) => (
                <tr key={s.submission_id}>
                  <td className="py-2.5">
                    <Link to={`/submissions/${s.submission_id}`} className="text-ink hover:text-forest font-medium">
                      {s.original_filename}
                    </Link>
                  </td>
                  <td className="py-2.5 text-slate">{s.student_name || "—"}</td>
                  <td className="py-2.5 text-slate">{s.assignment_title || "—"}</td>
                  <td className="py-2.5 text-slate capitalize">{s.status}</td>
                  <td className="py-2.5 font-mono text-slate">
                    {s.overall_originality_score !== null && s.overall_originality_score !== undefined
                      ? `${s.overall_originality_score.toFixed(0)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        ) : (
          <EmptyState title="No submissions yet" description="Submissions from your assignments will appear here as students upload them." />
        )}
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
