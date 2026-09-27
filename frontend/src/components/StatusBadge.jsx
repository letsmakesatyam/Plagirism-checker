const STYLES = {
  uploaded: "bg-slate/10 text-slate",
  extracting: "bg-brass/15 text-brass",
  extracted: "bg-brass/15 text-brass",
  embedding: "bg-brass/15 text-brass",
  embedded: "bg-forest/10 text-forest",
  failed: "bg-rust/10 text-rust",
  pending: "bg-slate/10 text-slate",
  generating: "bg-brass/15 text-brass",
  complete: "bg-forest/10 text-forest",
  likely_ai: "bg-rust/10 text-rust",
  uncertain: "bg-brass/15 text-brass",
  likely_human: "bg-forest/10 text-forest",
};

const LABELS = {
  uploaded: "Uploaded",
  extracting: "Extracting text",
  extracted: "Extracted",
  embedding: "Indexing",
  embedded: "Ready",
  failed: "Failed",
  pending: "Pending",
  generating: "Generating",
  complete: "Complete",
  likely_ai: "Likely AI",
  uncertain: "Uncertain",
  likely_human: "Likely human",
};

export default function StatusBadge({ status }) {
  if (!status) return null;
  const style = STYLES[status] || "bg-slate/10 text-slate";
  const label = LABELS[status] || status;
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium font-mono ${style}`}>
      {label}
    </span>
  );
}
