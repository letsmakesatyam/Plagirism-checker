import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import * as sourcesApi from "../../api/internetSources";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import { apiErrorMessage } from "../../api/client";

const CATEGORIES = [
  ["wikipedia", "Wikipedia"],
  ["research_paper", "Research paper"],
  ["book", "Book"],
  ["educational_website", "Educational website"],
  ["blog", "Blog"],
  ["government", "Government"],
];

export default function InternetSources() {
  const [mode, setMode] = useState("text");
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["internet-sources"],
    queryFn: sourcesApi.listInternetSources,
  });

  const { register, handleSubmit, reset } = useForm({ defaultValues: { category: "wikipedia" } });

  const addMutation = useMutation({
    mutationFn: (values) =>
      mode === "text"
        ? sourcesApi.addInternetSourceFromText(values)
        : sourcesApi.addInternetSourceFromUrl({ title: values.title, category: values.category, url: values.url }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["internet-sources"] });
      reset({ category: "wikipedia" });
    },
  });

  return (
    <div className="space-y-8">
      <header>
        <p className="eyebrow">Faculty</p>
        <h1 className="font-display text-3xl text-ink mt-1">Source library</h1>
        <p className="text-sm text-slate mt-1 max-w-2xl">
          Internet-plagiarism checks compare submissions against this locally indexed corpus rather than
          live web crawling. Add reference material here so the checker has something to compare against.
        </p>
      </header>

      <form onSubmit={handleSubmit((v) => addMutation.mutate(v))} className="card space-y-4">
        <ErrorBanner message={addMutation.error ? apiErrorMessage(addMutation.error, "Could not add this source.") : null} />
        <div className="flex gap-2">
          <button type="button" className={mode === "text" ? "btn-primary" : "btn-secondary"} onClick={() => setMode("text")}>
            Paste text
          </button>
          <button type="button" className={mode === "url" ? "btn-primary" : "btn-secondary"} onClick={() => setMode("url")}>
            From URL
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">Title</label>
            <input className="input" {...register("title", { required: true, minLength: 3 })} />
          </div>
          <div>
            <label className="label">Category</label>
            <select className="input" {...register("category")}>
              {CATEGORIES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
        </div>

        {mode === "text" ? (
          <>
            <div>
              <label className="label">Source text</label>
              <textarea className="input" rows={6} placeholder="Paste at least 50 characters of reference text…" {...register("text", { required: true, minLength: 50 })} />
            </div>
            <div>
              <label className="label">Source URL (optional, for attribution)</label>
              <input className="input" placeholder="https://…" {...register("url")} />
            </div>
          </>
        ) : (
          <div>
            <label className="label">URL to fetch</label>
            <input className="input" placeholder="https://…" {...register("url", { required: true })} />
          </div>
        )}

        <button type="submit" className="btn-primary" disabled={addMutation.isPending}>
          {addMutation.isPending ? "Indexing…" : "Add to library"}
        </button>
      </form>

      {isLoading ? (
        <Spinner label="Loading source library" />
      ) : error ? (
        <ErrorBanner message={apiErrorMessage(error, "Could not load the source library.")} />
      ) : data?.length ? (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto -mx-5 px-5 sm:mx-0 sm:px-0">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="bg-black/[0.02]">
              <tr className="text-left text-xs uppercase tracking-wide text-slate-light">
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Paragraphs</th>
                <th className="px-4 py-3 font-medium">Added</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-3 font-medium text-ink">
                    {s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="hover:text-forest">{s.title}</a> : s.title}
                  </td>
                  <td className="px-4 py-3 text-slate capitalize">{s.category.replace("_", " ")}</td>
                  <td className="px-4 py-3 font-mono text-slate">{s.paragraph_count}</td>
                  <td className="px-4 py-3 text-slate-light">{new Date(s.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : (
        <EmptyState title="Library is empty" description="Add reference sources above so internet-plagiarism checks have something to compare against." />
      )}
    </div>
  );
}
