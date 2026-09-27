import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import * as submissionsApi from "../../api/submissions";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import StatusBadge from "../../components/StatusBadge";
import { apiErrorMessage } from "../../api/client";

export default function MySubmissions() {
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["my-submissions", statusFilter, search],
    queryFn: () =>
      submissionsApi.listMySubmissions({
        ...(statusFilter ? { status_filter: statusFilter } : {}),
        ...(search ? { search } : {}),
      }),
    // Keep this list fresh on its own — a submission's status can change from
    // another request in flight, and without this you'd only see the update
    // after a manual page reload.
    refetchInterval: 5000,
  });

  return (
    <div className="space-y-6">
      <header>
        <p className="eyebrow">Student</p>
        <h1 className="font-display text-3xl text-ink mt-1">My submissions</h1>
      </header>

      <div className="flex gap-3">
        <input className="input max-w-xs" placeholder="Search filename…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="input max-w-[180px]" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="uploaded">Uploaded</option>
          <option value="extracting">Extracting</option>
          <option value="extracted">Extracted</option>
          <option value="embedding">Indexing</option>
          <option value="embedded">Ready</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {isLoading ? (
        <Spinner label="Loading your submissions" />
      ) : error ? (
        <ErrorBanner message={apiErrorMessage(error, "Could not load your submissions.")} />
      ) : data?.length ? (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto -mx-5 px-5 sm:mx-0 sm:px-0">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="bg-black/[0.02]">
              <tr className="text-left text-xs uppercase tracking-wide text-slate-light">
                <th className="px-4 py-3 font-medium">File</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Words</th>
                <th className="px-4 py-3 font-medium">Submitted</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((s) => (
                <tr key={s.id} className="hover:bg-black/[0.015]">
                  <td className="px-4 py-3 font-medium text-ink">{s.original_filename}</td>
                  <td className="px-4 py-3"><StatusBadge status={s.status} /></td>
                  <td className="px-4 py-3 font-mono text-slate">{s.word_count ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-light">{new Date(s.submitted_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <Link to={`/submissions/${s.id}`} className="text-forest hover:underline font-medium">
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : (
        <EmptyState title="No submissions yet" description="Upload an assignment to see its status and report here." />
      )}
    </div>
  );
}
