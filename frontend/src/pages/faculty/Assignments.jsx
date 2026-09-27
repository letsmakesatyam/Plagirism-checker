import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import * as assignmentsApi from "../../api/assignments";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import { apiErrorMessage } from "../../api/client";

export default function Assignments() {
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["assignments", search],
    queryFn: () => assignmentsApi.listAssignments(search ? { search } : {}),
  });

  const createMutation = useMutation({
    mutationFn: assignmentsApi.createAssignment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assignments"] });
      setShowForm(false);
    },
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Faculty</p>
          <h1 className="font-display text-3xl text-ink mt-1">Assignments</h1>
        </div>
        <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "New assignment"}
        </button>
      </header>

      {showForm && (
        <AssignmentForm
          onSubmit={(values) => createMutation.mutate(values)}
          submitting={createMutation.isPending}
          error={createMutation.error ? apiErrorMessage(createMutation.error, "Could not create assignment.") : null}
        />
      )}

      <input
        className="input max-w-sm"
        placeholder="Search by title or description…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <Spinner label="Loading assignments" />
      ) : error ? (
        <ErrorBanner message={apiErrorMessage(error, "Could not load assignments.")} />
      ) : data?.length ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {data.map((a) => (
            <Link key={a.id} to={`/faculty/assignments/${a.id}`} className="card hover:border-forest transition-colors block">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-display text-lg text-ink">{a.title}</h3>
                <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${a.is_active ? "bg-forest/10 text-forest" : "bg-slate/10 text-slate"}`}>
                  {a.is_active ? "Active" : "Closed"}
                </span>
              </div>
              {a.description && <p className="text-sm text-slate mt-2 line-clamp-2">{a.description}</p>}
              <div className="flex items-center justify-between mt-4 text-xs text-slate-light font-mono">
                <span>{a.submission_count} submission{a.submission_count === 1 ? "" : "s"}</span>
                {a.due_date && <span>Due {new Date(a.due_date).toLocaleDateString()}</span>}
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No assignments yet"
          description="Create your first assignment so students have somewhere to submit their work."
          action={<button className="btn-primary" onClick={() => setShowForm(true)}>New assignment</button>}
        />
      )}
    </div>
  );
}

export function AssignmentForm({ defaultValues, onSubmit, submitting, error }) {
  const { register, handleSubmit } = useForm({
    defaultValues: defaultValues || { title: "", description: "", due_date: "" },
  });

  return (
    <form
      onSubmit={handleSubmit((values) =>
        onSubmit({ ...values, due_date: values.due_date ? new Date(values.due_date).toISOString() : null })
      )}
      className="card space-y-4"
    >
      <ErrorBanner message={error} />
      <div>
        <label className="label">Title</label>
        <input className="input" {...register("title", { required: true, minLength: 3 })} />
      </div>
      <div>
        <label className="label">Description</label>
        <textarea className="input" rows={3} {...register("description")} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-end">
        <div>
          <label className="label">Due date</label>
          <input type="date" className="input" {...register("due_date")} />
        </div>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? "Saving…" : "Save assignment"}
        </button>
      </div>
    </form>
  );
}
