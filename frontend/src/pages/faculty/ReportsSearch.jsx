import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import * as reportsApi from "../../api/reports";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import { apiErrorMessage } from "../../api/client";

export default function ReportsSearch() {
  const [filters, setFilters] = useState({ search: "", status_filter: "", min_originality: "", max_originality: "" });

  const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== ""));
  const { data, isLoading, error } = useQuery({
    queryKey: ["reports", params],
    queryFn: () => reportsApi.listReports(params),
  });

  const set = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="space-y-6">
      <header>
        <p className="eyebrow">Faculty</p>
        <h1 className="font-display text-3xl text-ink mt-1">Report search</h1>
        <p className="text-sm text-slate mt-1">Search and filter every plagiarism report generated across your assignments.</p>
      </header>

      <div className="card flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-[200px]">
          <label className="label">Search</label>
          <input className="input" placeholder="Filename or student name…" value={filters.search} onChange={set("search")} />
        </div>
        <div>
          <label className="label">Status</label>
          <select className="input" value={filters.status_filter} onChange={set("status_filter")}>
            <option value="">Any</option>
            <option value="pending">Pending</option>
            <option value="generating">Generating</option>
            <option value="complete">Complete</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <div>
          <label className="label">Min originality %</label>
          <input type="number" min="0" max="100" className="input w-28" value={filters.min_originality} onChange={set("min_originality")} />
        </div>
        <div>
          <label className="label">Max originality %</label>
          <input type="number" min="0" max="100" className="input w-28" value={filters.max_originality} onChange={set("max_originality")} />
        </div>
      </div>

      {isLoading ? (
        <Spinner label="Loading reports" />
      ) : error ? (
        <ErrorBanner message={apiErrorMessage(error, "Could not load reports.")} />
      ) : data?.length ? (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto -mx-5 px-5 sm:mx-0 sm:px-0">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="bg-black/[0.02]">
              <tr className="text-left text-xs uppercase tracking-wide text-slate-light">
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Originality</th>
                <th className="px-4 py-3 font-medium">Internal</th>
                <th className="px-4 py-3 font-medium">Internet</th>
                <th className="px-4 py-3 font-medium">AI</th>
                <th className="px-4 py-3 font-medium">Generated</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((r) => (
                <tr key={r.id} className="hover:bg-black/[0.015]">
                  <td className="px-4 py-3 capitalize text-slate">{r.status}</td>
                  <td className="px-4 py-3 font-mono">{fmt(r.overall_originality_score)}</td>
                  <td className="px-4 py-3 font-mono text-slate">{fmt(r.internal_score)}</td>
                  <td className="px-4 py-3 font-mono text-slate">{fmt(r.internet_score)}</td>
                  <td className="px-4 py-3 font-mono text-slate">{fmt(r.ai_score)}</td>
                  <td className="px-4 py-3 text-slate-light">{r.generated_at ? new Date(r.generated_at).toLocaleString() : "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <Link to={`/submissions/${r.submission_id}`} className="text-forest hover:underline font-medium">
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : (
        <EmptyState title="No reports match" description="Try widening your filters, or generate reports from an assignment's submissions list." />
      )}
    </div>
  );
}

function fmt(v) {
  return v === null || v === undefined ? "—" : `${v.toFixed(0)}%`;
}
