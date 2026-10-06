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
import DocumentViewer from "../../components/DocumentViewer";

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
    onSuccess: (data) => {
      queryClient.setQueryData(["report", id], data);
      queryClient.invalidateQueries(["document-view", id]);
    },
  });

  const downloadPdf = async () => {
    const blob = await reportsApi.downloadReportPdf(id);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `plagiarism-report-${submission.original_filename.split(".")[0]}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  const highlightMap = useMemo(() => buildHighlightMap(report), [report]);
  const noReportYet = reportError?.response?.status === 404;

  if (subLoading) return <Spinner label="Loading submission" />;
  if (subError) return <ErrorBanner message={apiErrorMessage(subError, "Could not load this submission.")} />;

  // Determine AI display values
  const aiStatus = report?.ai_status;
  let aiDisplaySeal = {
    label: "AI writing signal",
    textValue: "—",
    status: aiStatus,
  };

  if (aiStatus === "insufficient_text") {
    aiDisplaySeal = { label: "AI writing signal", textValue: "Too short", status: "insufficient_text" };
  } else if (aiStatus === "unreliable_ocr") {
    aiDisplaySeal = { label: "AI writing signal", textValue: "Poor OCR", status: "unreliable_ocr" };
  } else if (aiStatus === "unavailable") {
    aiDisplaySeal = { label: "AI writing signal", textValue: "N/A", status: "unavailable" };
  } else if (aiStatus === "legacy") {
    aiDisplaySeal = {
      label: "AI writing signal",
      value: report.ai_score,
      textValue: report.ai_score !== null ? `${Math.round(report.ai_score)}%*` : "Legacy",
      status: "legacy",
    };
  } else if (aiStatus === "completed" && report.ai_signal_strength) {
    const strengthLabel =
      report.ai_signal_strength === "elevated"
        ? "Elevated"
        : report.ai_signal_strength === "low"
        ? "Low"
        : "Moderate";
    aiDisplaySeal = {
      label: "AI writing signal",
      textValue: strengthLabel,
      value: report.ai_signal_strength === "elevated" ? 75 : report.ai_signal_strength === "low" ? 15 : 45,
      status: report.ai_signal_strength,
      invert: true,
    };
  }

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
              Download PDF Report
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
          description="Run a check to get originality, internal-match, internet-match, and AI writing signal analysis."
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
              <ScoreSeal
                label={aiDisplaySeal.label}
                value={aiDisplaySeal.value}
                textValue={aiDisplaySeal.textValue}
                status={aiDisplaySeal.status}
                invert={aiDisplaySeal.invert}
                size={90}
              />
            </div>

            <div className="text-xs text-slate-light font-mono text-center mt-4 space-y-1">
              <p>
                Generated {report.generated_at ? new Date(report.generated_at).toLocaleString() : "—"} ·{" "}
                {report.paragraphs_checked ?? 0} paragraph(s) checked
              </p>
              {report.ai_word_coverage_pct !== null && report.ai_word_coverage_pct !== undefined && (
                <p>
                  AI prose coverage: {report.ai_word_coverage_pct}% ({report.ai_evaluated_words || 0} eligible prose words evaluated)
                </p>
              )}
            </div>

            {aiStatus === "legacy" && (
              <div className="mt-3 p-2 bg-amber-50 border border-amber-200 rounded-sm text-xs text-amber-800 text-center">
                * Note: This is a legacy AI score from an earlier version. Click &quot;Regenerate report&quot; above to re-evaluate with conservative prose windowing.
              </div>
            )}
          </section>

          <section className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <SummaryCard title="Legend">
              <LegendRow color="bg-rust/20 border-rust/40" label="Matches another submission (internal)" />
              <LegendRow color="bg-brass/20 border-brass/40" label="Matches an indexed source (internet)" />
              <LegendRow color="bg-violet/20 border-violet/40" label="AI writing signal (review required)" />
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
                Tip: submission IDs are visible in an assignment&apos;s submission list, where you can also select two rows to compare directly.
              </p>
            </section>
          )}

          <p className="text-xs text-slate-light max-w-2xl">
            AI writing signal note: this classifier provides a statistical pattern indicator, not definitive proof of authorship.
            Borderline or short passages require human academic judgment. Originality and plagiarism scores remain completely separate.
          </p>
        </>
      )}

      {/* Real layout document viewer with interactive in-doc highlighting */}
      {submission && (
        <DocumentViewer
          submissionId={id}
          originalFilename={submission.original_filename}
          report={report}
          paragraphs={submission.paragraphs || []}
          highlightMap={highlightMap}
          isFaculty={isFaculty}
          paragraphStyle={paragraphStyle}
        />
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
    const label = typeof r.label === "string" ? r.label : r.label?.value;
    if (label === "likely_ai") add(r.paragraph_index, "ai");
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
