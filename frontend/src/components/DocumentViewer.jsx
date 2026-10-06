import { useState, useMemo, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import * as submissionsApi from "../api/submissions";
import Spinner from "./Spinner";

export default function DocumentViewer({
  submissionId,
  originalFilename,
  report,
  paragraphs = [],
  highlightMap = {},
  isFaculty = false,
  paragraphStyle = () => "bg-black/[0.015] border-line",
}) {
  const [viewMode, setViewMode] = useState("document"); // "document" | "text"
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [activeFilter, setActiveFilter] = useState("all"); // "all" | "internal" | "internet" | "ai"
  const [showAnnotations, setShowAnnotations] = useState(true);
  const [activeHighlight, setActiveHighlight] = useState(null);
  const [downloadingAnnotated, setDownloadingAnnotated] = useState(false);
  const [downloadingOriginal, setDownloadingOriginal] = useState(false);
  const [downloadError, setDownloadError] = useState(null);

  // Authenticated page image state
  const [pageImageUrl, setPageImageUrl] = useState(null);
  const [imageLoading, setImageLoading] = useState(true);
  const [imageError, setImageError] = useState(null);

  const {
    data: docView,
    isLoading: docLoading,
    error: docError,
    refetch: refetchDocView,
  } = useQuery({
    queryKey: ["document-view", submissionId],
    queryFn: () => submissionsApi.getDocumentView(submissionId),
    retry: 1,
  });

  const totalPages = docView?.page_count || 1;
  const currentPageData = useMemo(() => {
    if (!docView?.pages || docView.pages.length === 0) return null;
    return docView.pages.find((p) => p.page_number === currentPage) || docView.pages[0];
  }, [docView, currentPage]);

  // Reset active highlight when navigating to another page
  useEffect(() => {
    setActiveHighlight(null);
  }, [currentPage]);

  // Load authenticated page image as blob via Axios
  useEffect(() => {
    if (!submissionId || !currentPageData) return;

    let isMounted = true;
    let objectUrl = null;

    setImageLoading(true);
    setImageError(null);

    submissionsApi
      .getPageImageBlob(submissionId, currentPage, false)
      .then((blob) => {
        if (!isMounted) return;
        objectUrl = window.URL.createObjectURL(blob);
        setPageImageUrl(objectUrl);
        setImageLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        setImageError("Could not render page image.");
        setImageLoading(false);
      });

    return () => {
      isMounted = false;
      if (objectUrl) {
        window.URL.revokeObjectURL(objectUrl);
      }
    };
  }, [submissionId, currentPage, currentPageData]);

  const visibleHighlights = useMemo(() => {
    if (!currentPageData?.highlights) return [];
    if (activeFilter === "all") return currentPageData.highlights;
    return currentPageData.highlights.filter((h) => h.type === activeFilter);
  }, [currentPageData, activeFilter]);

  const unmappedHighlights = useMemo(() => {
    if (!docView?.unmapped_highlights) return [];
    if (activeFilter === "all") return docView.unmapped_highlights;
    return docView.unmapped_highlights.filter((h) => h.type === activeFilter);
  }, [docView, activeFilter]);

  const handleDownloadOriginal = async () => {
    try {
      setDownloadingOriginal(true);
      setDownloadError(null);
      const blob = await submissionsApi.downloadOriginalFile(submissionId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = originalFilename || "original_submission";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError("Failed to download original file. Please try again.");
    } finally {
      setDownloadingOriginal(false);
    }
  };

  const handleDownloadAnnotated = async () => {
    try {
      setDownloadingAnnotated(true);
      setDownloadError(null);
      const blob = await submissionsApi.downloadAnnotatedDocument(submissionId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const cleanStem = (originalFilename || "submission").replace(/\.[^/.]+$/, "");
      a.download = `annotated-${cleanStem}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError("Failed to download annotated document. Please try again.");
    } finally {
      setDownloadingAnnotated(false);
    }
  };

  const getHighlightColor = (type) => {
    if (type === "internal") {
      return {
        bg: "bg-rust/25 hover:bg-rust/40",
        pill: "bg-rust/10 text-rust border-rust/30",
        badge: "bg-rust text-white",
      };
    }
    if (type === "internet") {
      return {
        bg: "bg-brass/25 hover:bg-brass/40",
        pill: "bg-brass/10 text-brass border-brass/30",
        badge: "bg-brass text-white",
      };
    }
    // AI signal
    return {
      bg: "bg-violet/25 hover:bg-violet/40",
      pill: "bg-violet/10 text-violet border-violet/30",
      badge: "bg-violet text-white",
    };
  };

  return (
    <section className="card space-y-4">
      {/* Top Bar: View Mode Switcher and Action Buttons */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-line">
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-sm border border-line p-0.5 bg-paper/60">
            <button
              type="button"
              onClick={() => setViewMode("document")}
              className={`px-3 py-1.5 text-xs font-medium rounded-sm transition-colors flex items-center gap-1.5 ${
                viewMode === "document"
                  ? "bg-white text-forest shadow-xs font-semibold"
                  : "text-slate hover:text-ink"
              }`}
            >
              <span>📄</span> Document View (Real Layout)
            </button>
            <button
              type="button"
              onClick={() => setViewMode("text")}
              className={`px-3 py-1.5 text-xs font-medium rounded-sm transition-colors flex items-center gap-1.5 ${
                viewMode === "text"
                  ? "bg-white text-forest shadow-xs font-semibold"
                  : "text-slate hover:text-ink"
              }`}
            >
              <span>📝</span> Extracted Text View
            </button>
          </div>

          {docView?.preview_label && (
            <span className="text-3xs font-mono uppercase tracking-wider px-2 py-0.5 rounded-sm bg-slate-light/15 text-slate border border-line">
              {docView.preview_label}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleDownloadOriginal}
            disabled={downloadingOriginal}
            className="btn-secondary text-xs py-1.5 px-3 h-8"
            title="Download original uploaded file unchanged"
          >
            {downloadingOriginal ? "Downloading…" : "💾 Download Original"}
          </button>

          {viewMode === "document" && docView?.pages?.length > 0 && (
            <button
              type="button"
              onClick={handleDownloadAnnotated}
              disabled={downloadingAnnotated}
              className="btn-secondary text-xs py-1.5 px-3 h-8"
              title="Download PDF document with visual highlights embedded"
            >
              {downloadingAnnotated ? "Preparing PDF…" : "📥 Download Annotated PDF"}
            </button>
          )}
        </div>
      </div>

      {downloadError && (
        <div className="p-2.5 text-xs text-rust bg-rust/10 border border-rust/30 rounded-sm">
          {downloadError}
        </div>
      )}

      {/* DOCUMENT VIEW */}
      {viewMode === "document" && (
        <div className="space-y-4">
          {/* Controls Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 bg-paper/40 p-2.5 rounded-sm border border-line text-xs">
            {/* Page Navigation */}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1 || totalPages <= 1}
                className="px-2 py-1 rounded-sm border border-line bg-white hover:bg-paper disabled:opacity-40 transition-colors"
                title="Previous page"
              >
                ← Prev
              </button>

              <span className="font-mono px-2 text-ink">
                Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
              </span>

              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages || totalPages <= 1}
                className="px-2 py-1 rounded-sm border border-line bg-white hover:bg-paper disabled:opacity-40 transition-colors"
                title="Next page"
              >
                Next →
              </button>
            </div>

            {/* Filter Pills */}
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-slate text-2xs uppercase tracking-wider font-medium mr-1">Filter:</span>
              <button
                type="button"
                onClick={() => setActiveFilter("all")}
                className={`px-2 py-0.5 rounded-sm border transition-colors ${
                  activeFilter === "all"
                    ? "bg-forest text-white border-forest"
                    : "bg-white text-slate border-line hover:text-ink"
                }`}
              >
                All ({docView?.summary?.total_highlights ?? 0})
              </button>

              {(docView?.summary?.internal_count ?? 0) > 0 && (
                <button
                  type="button"
                  onClick={() => setActiveFilter("internal")}
                  className={`px-2 py-0.5 rounded-sm border transition-colors ${
                    activeFilter === "internal"
                      ? "bg-rust text-white border-rust"
                      : "bg-white text-rust border-rust/30 hover:bg-rust/5"
                  }`}
                >
                  Internal ({docView.summary.internal_count})
                </button>
              )}

              {(docView?.summary?.internet_count ?? 0) > 0 && (
                <button
                  type="button"
                  onClick={() => setActiveFilter("internet")}
                  className={`px-2 py-0.5 rounded-sm border transition-colors ${
                    activeFilter === "internet"
                      ? "bg-brass text-white border-brass"
                      : "bg-white text-brass border-brass/30 hover:bg-brass/5"
                  }`}
                >
                  Internet ({docView.summary.internet_count})
                </button>
              )}

              {(docView?.summary?.ai_count ?? 0) > 0 && (
                <button
                  type="button"
                  onClick={() => setActiveFilter("ai")}
                  className={`px-2 py-0.5 rounded-sm border transition-colors ${
                    activeFilter === "ai"
                      ? "bg-violet text-white border-violet"
                      : "bg-white text-violet border-violet/30 hover:bg-violet/5"
                  }`}
                >
                  AI Signal ({docView.summary.ai_count})
                </button>
              )}
            </div>

            {/* Display Options & Zoom */}
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 cursor-pointer text-slate hover:text-ink select-none">
                <input
                  type="checkbox"
                  checked={showAnnotations}
                  onChange={(e) => setShowAnnotations(e.target.checked)}
                  className="rounded-xs text-forest focus:ring-forest"
                />
                <span>Show Highlights</span>
              </label>

              <div className="h-3.5 w-px bg-line" />

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setZoom((z) => Math.max(0.6, Math.round((z - 0.2) * 10) / 10))}
                  className="w-6 h-6 flex items-center justify-center rounded-sm border border-line bg-white hover:bg-paper"
                  title="Zoom Out"
                >
                  −
                </button>
                <span className="font-mono text-2xs w-9 text-center text-slate">
                  {Math.round(zoom * 100)}%
                </span>
                <button
                  type="button"
                  onClick={() => setZoom((z) => Math.min(2.5, Math.round((z + 0.2) * 10) / 10))}
                  className="w-6 h-6 flex items-center justify-center rounded-sm border border-line bg-white hover:bg-paper"
                  title="Zoom In"
                >
                  +
                </button>
                <button
                  type="button"
                  onClick={() => setZoom(1.0)}
                  className="px-1.5 py-0.5 text-2xs rounded-sm border border-line bg-white hover:bg-paper text-slate"
                  title="Reset Zoom"
                >
                  Reset
                </button>
              </div>
            </div>
          </div>

          {/* Loading and Error States */}
          {docLoading && (
            <div className="py-20 flex justify-center">
              <Spinner label="Rendering document layout…" />
            </div>
          )}

          {docError && (
            <div className="p-6 text-center text-sm text-rust bg-rust/5 rounded-sm border border-rust/20 space-y-2">
              <p>Could not load document preview for this submission.</p>
              <button
                type="button"
                onClick={() => refetchDocView()}
                className="btn-secondary text-xs py-1 px-3"
              >
                Retry
              </button>
            </div>
          )}

          {/* Document Canvas Container with Full Scroll Support */}
          {!docLoading && !docError && currentPageData && (
            <div className="relative overflow-auto p-4 bg-slate-light/10 rounded-sm border border-line flex justify-center max-h-[85vh]">
              <div
                className="relative bg-white shadow-md border border-line origin-top shrink-0"
                style={{
                  width: `${Math.round(Math.min(900, (currentPageData.width || 595) * 1.3) * zoom)}px`,
                }}
              >
                {imageLoading && (
                  <div className="absolute inset-0 flex items-center justify-center bg-white/70 z-10">
                    <Spinner label="Loading page image…" />
                  </div>
                )}

                {imageError && (
                  <div className="p-12 text-center text-xs text-rust">
                    {imageError}
                  </div>
                )}

                {pageImageUrl && (
                  <img
                    src={pageImageUrl}
                    alt={`Document Page ${currentPage}`}
                    className="w-full h-auto block select-none pointer-events-none"
                    loading="eager"
                  />
                )}

                {/* Interactive Highlight Overlays */}
                {showAnnotations && !imageLoading && (
                  <div className="absolute inset-0 pointer-events-none">
                    {visibleHighlights.map((hl) => {
                      const colors = getHighlightColor(hl.type);
                      const isSelected = activeHighlight?.id === hl.id;

                      return (hl.rects || []).map((r, rectIdx) => (
                        <div
                          key={`${hl.id}_${rectIdx}`}
                          onClick={() => setActiveHighlight(isSelected ? null : hl)}
                          onMouseEnter={() => setActiveHighlight(hl)}
                          className={`absolute pointer-events-auto cursor-pointer rounded-xs transition-all duration-150 ${colors.bg} ${
                            isSelected
                              ? "ring-2 ring-forest ring-offset-1 bg-opacity-50"
                              : "hover:ring-1 hover:ring-forest/50"
                          }`}
                          style={{
                            left: `${r.left_pct}%`,
                            top: `${r.top_pct}%`,
                            width: `${r.width_pct}%`,
                            height: `${r.height_pct}%`,
                          }}
                          title={`${hl.title}: ${hl.badge}`}
                        />
                      ));
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Active Highlight Detail Inspector */}
          {activeHighlight && (
            <div className="p-3 bg-white border border-line rounded-sm shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-block px-2 py-0.5 rounded-sm font-medium text-2xs ${
                      getHighlightColor(activeHighlight.type).pill
                    }`}
                  >
                    {activeHighlight.title}
                  </span>
                  <span className="font-mono text-slate-light">
                    Paragraph #{activeHighlight.paragraph_index + 1} · {activeHighlight.evidence_kind}
                  </span>
                </div>
                <p className="text-slate text-sm">{activeHighlight.description}</p>
                {activeHighlight.matched_text && (
                  <p className="text-2xs font-mono text-slate-light bg-paper/60 p-1.5 rounded-xs border border-line/60">
                    Matched text snippet: "{activeHighlight.matched_text}…"
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {isFaculty && activeHighlight.type === "internal" && (
                  <Link
                    to={`/faculty/compare/${submissionId}/${activeHighlight.matched_submission_id || ""}`}
                    className="btn-secondary text-xs py-1 px-2.5"
                  >
                    Compare side-by-side →
                  </Link>
                )}
                <button
                  type="button"
                  onClick={() => setActiveHighlight(null)}
                  className="text-slate hover:text-ink px-2 py-1 text-xs"
                >
                  Dismiss ✕
                </button>
              </div>
            </div>
          )}

          {/* Unmapped Evidence Drawer (shows matches where layout coordinates were unavailable) */}
          {unmappedHighlights.length > 0 && (
            <div className="p-3 bg-paper/60 border border-line rounded-sm text-xs space-y-2">
              <p className="font-medium text-slate">
                Matches without precise layout coordinates ({unmappedHighlights.length}):
              </p>
              <div className="space-y-1.5">
                {unmappedHighlights.map((uh, i) => (
                  <div key={i} className="flex items-center justify-between text-2xs text-slate bg-white p-2 rounded-xs border border-line">
                    <div>
                      <span className="font-medium text-ink mr-2">{uh.title}</span>
                      <span>Paragraph #{uh.paragraph_index + 1} — {uh.status_text}</span>
                    </div>
                    {isFaculty && uh.type === "internal" && uh.matched_submission_id && (
                      <Link
                        to={`/faculty/compare/${submissionId}/${uh.matched_submission_id}`}
                        className="text-forest hover:underline shrink-0 ml-2"
                      >
                        Compare →
                      </Link>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* EXTRACTED TEXT VIEW (SECONDARY VIEW) */}
      {viewMode === "text" && (
        <div className="space-y-4 pt-1">
          <p className="text-xs text-slate-light">
            Extracted text view showing normalized paragraphs and evidence flags.
          </p>
          <div className="space-y-3">
            {paragraphs.map((text, index) => {
              const flags = highlightMap[index] || [];
              return (
                <div
                  key={index}
                  className={`text-sm leading-relaxed p-3.5 rounded-sm border transition-colors ${paragraphStyle(
                    flags
                  )}`}
                >
                  <div className="flex items-center justify-between text-2xs text-slate-light font-mono mb-1">
                    <span>Paragraph #{index + 1}</span>
                    {flags.length > 0 && (
                      <span className="capitalize font-medium text-ink">
                        Flagged: {flags.join(", ")}
                      </span>
                    )}
                  </div>
                  <p className="whitespace-pre-line">{text}</p>
                </div>
              );
            })}
            {!paragraphs.length && (
              <p className="text-sm text-slate-light">No paragraph text stored for this submission.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
