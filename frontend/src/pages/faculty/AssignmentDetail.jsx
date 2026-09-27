import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as assignmentsApi from "../../api/assignments";
import * as submissionsApi from "../../api/submissions";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import StatusBadge from "../../components/StatusBadge";
import { apiErrorMessage } from "../../api/client";
import { AssignmentForm } from "./Assignments";

export default function AssignmentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [compareSelection, setCompareSelection] = useState([]);

  const { data: assignment, isLoading, error } = useQuery({
    queryKey: ["assignment", id],
    queryFn: () => assignmentsApi.getAssignment(id),
  });

  const { data: submissions, isLoading: subsLoading } = useQuery({
    queryKey: ["assignment-submissions", id, statusFilter, search],
    queryFn: () =>
      submissionsApi.listAssignmentSubmissions(id, {
        ...(statusFilter ? { status_filter: statusFilter } : {}),
        ...(search ? { search } : {}),
      }),
    // Keep statuses fresh without requiring a manual reload while a
    // student's upload is still being processed.
    refetchInterval: 5000,
  });

  const updateMutation = useMutation({
    mutationFn: (values) => assignmentsApi.updateAssignment(id, values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assignment", id] });
      setEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => assignmentsApi.deleteAssignment(id),
    onSuccess: () => navigate("/faculty/assignments"),
  });

  const toggleCompare = (submissionId) => {
    setCompareSelection((prev) => {
      if (prev.includes(submissionId)) return prev.filter((x) => x !== submissionId);
      if (prev.length >= 2) return [prev[1], submissionId];
      return [...prev, submissionId];
    });
  };

  if (isLoading) return <Spinner label="Loading assignment" />;
  if (error) return <ErrorBanner message={apiErrorMessage(error, "Could not load this assignment.")} />;

  return (
    <div className="space-y-8">
      <div>
        <Link to="/faculty/assignments" className="text-sm text-slate hover:text-forest">← All assignments</Link>
      </div>

      {editing ? (
        <AssignmentForm
          defaultValues={{
            title: assignment.title,
            description: assignment.description || "",
            due_date: assignment.due_date ? assignment.due_date.slice(0, 10) : "",
          }}
          onSubmit={(values) => updateMutation.mutate(values)}
          submitting={updateMutation.isPending}
          error={updateMutation.error ? apiErrorMessage(updateMutation.error) : null}
        />
      ) : (
        <header className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <p className="eyebrow">{assignment.is_active ? "Active assignment" : "Closed assignment"}</p>
            <h1 className="font-display text-3xl text-ink mt-1">{assignment.title}</h1>
            {assignment.description && <p className="text-slate mt-2 max-w-2xl">{assignment.description}</p>}
            {assignment.due_date && (
              <p className="text-xs font-mono text-slate-light mt-2">
                Due {new Date(assignment.due_date).toLocaleDateString()}
              </p>
            )}
          </div>
          <div className="flex gap-2 shrink-0">
            <button className="btn-secondary" onClick={() => setEditing(true)}>Edit</button>
            <button
              className="btn-danger"
              onClick={() => {
                if (confirm("Delete this assignment? This cannot be undone.")) deleteMutation.mutate();
              }}
              disabled={deleteMutation.isPending}
            >
              Delete
            </button>
          </div>
        </header>
      )}

      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <h2 className="font-display text-xl">Submissions</h2>
          {compareSelection.length === 2 && (
            <button
              className="btn-primary"
              onClick={() => navigate(`/faculty/compare/${compareSelection[0]}/${compareSelection[1]}`)}
            >
              Compare selected (2)
            </button>
          )}
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <input
            className="input sm:max-w-xs"
            placeholder="Search filename or student…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
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

        {subsLoading ? (
          <Spinner label="Loading submissions" />
        ) : submissions?.length ? (
          <div className="card p-0 overflow-hidden">
            <div className="overflow-x-auto -mx-5 px-5 sm:mx-0 sm:px-0">
          <table className="w-full text-sm min-w-[640px]">
              <thead className="bg-black/[0.02]">
                <tr className="text-left text-xs uppercase tracking-wide text-slate-light">
                  <th className="px-4 py-3 font-medium w-8"></th>
                  <th className="px-4 py-3 font-medium">File</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Words</th>
                  <th className="px-4 py-3 font-medium">Submitted</th>
                  <th className="px-4 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {submissions.map((s) => (
                  <tr key={s.id} className="hover:bg-black/[0.015]">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={compareSelection.includes(s.id)}
                        onChange={() => toggleCompare(s.id)}
                        disabled={s.status !== "embedded" && !compareSelection.includes(s.id)}
                      />
                    </td>
                    <td className="px-4 py-3 font-medium text-ink">{s.original_filename}</td>
                    <td className="px-4 py-3"><StatusBadge status={s.status} /></td>
                    <td className="px-4 py-3 font-mono text-slate">{s.word_count ?? "—"}</td>
                    <td className="px-4 py-3 text-slate-light">{new Date(s.submitted_at).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">
                      <Link to={`/submissions/${s.id}`} className="text-forest hover:underline font-medium">
                        View report →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        ) : (
          <EmptyState title="No submissions yet" description="Submissions will appear here once students upload their work." />
        )}
      </section>
    </div>
  );
}
