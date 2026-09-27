import { useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as submissionsApi from "../../api/submissions";
import * as reportsApi from "../../api/reports";
import { useAuth } from "../../context/AuthContext";
import { apiErrorMessage } from "../../api/client";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import ScoreSeal from "../../components/ScoreSeal";
import EmptyState from "../../components/EmptyState";

export default function SubmissionReport() {
  const { id } = useParams();
  const { isFaculty } = useAuth();
  const queryClient = useQueryClient();
  const [compareTarget, setCompareTarget] = useState("");

  const { data: submission, isLoading: subLoading, error: subError } = useQuery({
    queryKey: ["submission", id],
    queryFn: () => submissionsApi.getSubmission(id),
  });

  const {
    data: report,
    isLoading: reportLoading,
    error: reportError,
  } = useQuery({
    queryKey: ["report", id],
    queryFn: () => reportsApi.getReport(id),
    retry: false,
    enabled: !!submission,
  });

  const generateMutation = useMutation({
    mutationFn: () => reportsApi.generateReport(id),
    onSuccess: (data) => queryClient.setQueryData(["report", id], data),
  });

  const downloadPdf = async () => {
    const blob = await reportsApi.downloadReportPdf(id);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `plagiarism-report-${submission.original_filename.split(".")[0]}.pdf`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  const highlightMap = useMemo(() => buildHighlightMap(report), [report]);
  const noReportYet = reportError?.response?.status === 404;

  if (subLoading) return <Spinner label="Loading submission" />;
  if (subError) return <ErrorBanner message={apiErrorMessage(subError, "Could not load this submission.")} />;

  return (
    <div className="space-y-8">
      <div>
        <Link to={isFaculty ? "/faculty/reports" : "/student/submissions"} className="text-sm text-slate hover:text-forest">
          ← Back
        </Link>
      </div>

      <header className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 sm:gap-6">
        <div className="min-w-0">
          <p className="eyebrow">{submission.file_type?.toUpperCase()} submission</p>
          <h1 className="font-display text-2xl text-ink mt-1 break-words">{submission.original_filename}</h1>
          <div className="flex items-center gap-3 mt-2">
            <StatusBadge status={submission.status} />
            <span className="text-xs font-mono text-slate-light">
              {submission.word_count ?? "—"} words · {submission.page_count ?? "—"} page(s)
              {submission.was_ocr_used ? " · OCR used" : ""}
            </span>
          </div>
          {submission.extraction_error && <p className="text-xs text-rust mt-2">Extraction error: {submission.extraction_error}</p>}
          {submission.embedding_error && <p className="text-xs text-rust mt-2">Indexing error: {submission.embedding_error}</p>}
        </div>

        <div className="flex flex-wrap gap-2 shrink-0">
          {submission.status === "embedded" && (
            <button className="btn-secondary" onClick={() => generateMutation.mutate()} disabled={generateMutation.isPending}>
              {generateMutation.isPending ? "Generating…" : report ? "Regenerate report" : "Generate report"}
            </button>
          )}
          {report && (
            <button className="btn-primary" onClick={downloadPdf}>
              Download PDF
            </button>
          )}
        </div>
      </header>

      {generateMutation.error && <ErrorBanner message={apiErrorMessage(generateMutation.error, "Could not generate the report.")} />}

      {submission.status === "failed" && !report && (
        <EmptyState
          title="Submission processing failed"
          description={
            submission.extraction_error ||
            submission.embedding_error ||
            "An error occurred while processing this file. Please check that the file contains legible text and try uploading again."
          }
        />
      )}

      {submission.status !== "embedded" && submission.status !== "failed" && !report && (
        <EmptyState
          title="Not ready for a report yet"
          description="This submission needs to finish text extraction and indexing before a plagiarism report can be generated. Refresh in a moment."
        />
      )}

      {reportLoading && submission.status === "embedded" && <Spinner label="Loading report" />}

      {noReportYet && submission.status === "embedded" && (
        <EmptyState
          title="No report generated yet"
          description="Run a check to get originality, internal-match, internet-match, and AI-detection scores."
          action={
            <button className="btn-primary" onClick={() => generateMutation.mutate()} disabled={generateMutation.isPending}>
              {generateMutation.isPending ? "Generating…" : "Generate report"}
            </button>
          }
        />
      )}

      {report && report.status === "complete" && (
        <>
          <section className="card">
            <div className="flex flex-wrap gap-8 justify-around">
              <ScoreSeal label="Originality" value={report.overall_originality_score} size={110} />
              <ScoreSeal label="Internal match" value={report.internal_score} invert size={90} />
              <ScoreSeal label="Internet match" value={report.internet_score} invert size={90} />
              <ScoreSeal label="AI likelihood" value={report.ai_score} invert size={90} />
            </div>
            <p className="text-xs text-slate-light font-mono text-center mt-4">
              generated {report.generated_at ? new Date(report.generated_at).toLocaleString() : "—"} ·
              {" "}{report.paragraphs_checked ?? 0} paragraph(s) checked
            </p>
          </section>

          <section className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <SummaryCard title="Legend">
              <LegendRow color="bg-rust/20 border-rust/40" label="Matches another submission (internal)" />
              <LegendRow color="bg-brass/20 border-brass/40" label="Matches an indexed source (internet)" />
              <LegendRow color="bg-violet/20 border-violet/40" label="Likely AI-generated" />
            </SummaryCard>
            <SummaryCard title="Copied from">
              {report.copied_from?.length ? (
                report.copied_from.map((c) => (
                  <p key={c.matched_submission_id} className="text-sm text-slate">
                    <span className="text-ink font-medium">{c.matched_student_name || "Unknown student"}</span> —{" "}
                    {c.paragraphs_matched} paragraph(s), avg {(c.average_similarity * 100).toFixed(0)}%
                    {isFaculty && (
                      <>
                        {" "}
                        <Link to={`/faculty/compare/${id}/${c.matched_submission_id}`} className="text-forest hover:underline">
                          compare →
                        </Link>
                      </>
                    )}
                  </p>
                ))
              ) : (
                <p className="text-sm text-slate-light">No internal matches found.</p>
              )}
            </SummaryCard>
            <SummaryCard title="Internet sources matched">
              {report.internet_sources?.length ? (
                report.internet_sources.map((s) => (
                  <p key={s.matched_source_id} className="text-sm text-slate">
                    <span className="text-ink font-medium">{s.title}</span> — {s.percentage_of_submission.toFixed(0)}% of submission
                  </p>
                ))
              ) : (
                <p className="text-sm text-slate-light">No internet-source matches found.</p>
              )}
            </SummaryCard>
          </section>

          {isFaculty && (
            <section className="card">
              <h2 className="font-display text-lg mb-3">Compare with another submission</h2>
              <div className="flex gap-2">
                <input
                  className="input max-w-md"
                  placeholder="Paste another submission's ID…"
                  value={compareTarget}
                  onChange={(e) => setCompareTarget(e.target.value)}
                />
                <Link
                  to={compareTarget ? `/faculty/compare/${id}/${compareTarget}` : "#"}
                  className={`btn-secondary ${!compareTarget ? "pointer-events-none opacity-50" : ""}`}
                >
                  Compare
                </Link>
              </div>
              <p className="text-xs text-slate-light mt-2">
                Tip: submission IDs are visible in an assignment's submission list, where you can also select two rows to compare directly.
              </p>
            </section>
          )}

          <section className="card">
            <h2 className="font-display text-lg mb-4">Full text with highlights</h2>
            <div className="space-y-3">
              {(submission.paragraphs || []).map((text, index) => {
                const flags = highlightMap[index] || [];
                return (
                  <p
                    key={index}
                    className={`text-sm leading-relaxed p-3 rounded-sm border ${paragraphStyle(flags)}`}
                  >
                    {text}
                  </p>
                );
              })}
              {!submission.paragraphs?.length && <p className="text-sm text-slate-light">No paragraph text stored for this submission.</p>}
            </div>
          </section>

          <p className="text-xs text-slate-light max-w-2xl">
            AI-detection note: this uses an open-source classifier trained primarily on older
            (GPT-2-era) generated text. Treat the AI-likelihood score as a rough signal, not
            proof — always review flagged paragraphs yourself before drawing conclusions.
          </p>
        </>
      )}

      {report && report.status === "failed" && <ErrorBanner message={report.error || "Report generation failed."} />}
    </div>
  );
}

function buildHighlightMap(report) {
  const map = {};
  if (!report) return map;
  const add = (index, flag) => {
    if (index === null || index === undefined) return;
    if (!map[index]) map[index] = [];
    if (!map[index].includes(flag)) map[index].push(flag);
  };
  (report.internal_matches || []).forEach((m) => add(m.source_paragraph_index, "internal"));
  (report.internet_matches || []).forEach((m) => add(m.source_paragraph_index, "internet"));
  (report.ai_results || []).forEach((r) => {
    if (r.label === "likely_ai") add(r.paragraph_index, "ai");
  });
  return map;
}

function paragraphStyle(flags) {
  if (flags.includes("internal")) return "bg-rust/5 border-rust/30";
  if (flags.includes("internet")) return "bg-brass/5 border-brass/30";
  if (flags.includes("ai")) return "bg-violet/5 border-violet/30";
  return "bg-black/[0.015] border-line";
}

function SummaryCard({ title, children }) {
  return (
    <div className="card">
      <h3 className="font-display text-base mb-3">{title}</h3>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function LegendRow({ color, label }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-3 w-3 rounded-sm border ${color}`} />
      <span className="text-xs text-slate">{label}</span>
    </div>
  );
}
