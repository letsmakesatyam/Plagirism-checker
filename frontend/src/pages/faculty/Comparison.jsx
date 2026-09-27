import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import * as reportsApi from "../../api/reports";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import { apiErrorMessage } from "../../api/client";

export default function Comparison() {
  const { aId, bId } = useParams();
  const { data, isLoading, error } = useQuery({
    queryKey: ["compare", aId, bId],
    queryFn: () => reportsApi.compareSubmissions(aId, bId),
  });

  if (isLoading) return <Spinner label="Comparing submissions" />;
  if (error) {
    return (
      <ErrorBanner
        message={apiErrorMessage(
          error,
          "Could not compare these submissions. Both need a generated report first."
        )}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/faculty/reports" className="text-sm text-slate hover:text-forest">← Back to reports</Link>
      </div>
      <header className="flex items-center justify-between">
        <div>
          <p className="eyebrow">Comparison</p>
          <h1 className="font-display text-3xl text-ink mt-1">Submission comparison</h1>
        </div>
        <div className="text-right">
          <p className="text-xs uppercase tracking-wide text-slate">Matched paragraphs</p>
          <p className="font-display text-2xl text-forest">{data.matched_paragraph_count}</p>
          {data.average_similarity !== null && data.average_similarity !== undefined && (
            <p className="text-xs font-mono text-slate-light">avg similarity {(data.average_similarity * 100).toFixed(0)}%</p>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ComparisonColumn title="Submission A" submissionId={data.submission_a_id} paragraphs={data.a_paragraphs} />
        <ComparisonColumn title="Submission B" submissionId={data.submission_b_id} paragraphs={data.b_paragraphs} />
      </div>
    </div>
  );
}

function ComparisonColumn({ title, submissionId, paragraphs }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-display text-lg">{title}</h2>
        <Link to={`/submissions/${submissionId}`} className="text-xs text-forest hover:underline font-mono">
          view full report →
        </Link>
      </div>
      <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
        {paragraphs.map((p) => (
          <div
            key={p.paragraph_index}
            className={`text-sm rounded-sm p-3 border ${
              p.matched_paragraph_index !== null && p.matched_paragraph_index !== undefined
                ? "bg-rust/5 border-rust/20"
                : "bg-black/[0.015] border-line"
            }`}
          >
            <p className="text-ink leading-relaxed">{p.paragraph_text}</p>
            {p.similarity !== null && p.similarity !== undefined && (
              <p className="text-xs font-mono text-rust mt-2">matched · {(p.similarity * 100).toFixed(0)}% similar</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
