import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as assignmentsApi from "../../api/assignments";
import * as submissionsApi from "../../api/submissions";
import Spinner from "../../components/Spinner";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import { apiErrorMessage } from "../../api/client";
import { useNavigate } from "react-router-dom";

export default function StudentAssignments() {
  const [search, setSearch] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["assignments", search],
    queryFn: () => assignmentsApi.listAssignments(search ? { search } : {}),
  });

  return (
    <div className="space-y-6">
      <header>
        <p className="eyebrow">Student</p>
        <h1 className="font-display text-3xl text-ink mt-1">Assignments</h1>
      </header>

      <input
        className="input max-w-sm"
        placeholder="Search assignments…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <Spinner label="Loading assignments" />
      ) : error ? (
        <ErrorBanner message={apiErrorMessage(error, "Could not load assignments.")} />
      ) : data?.length ? (
        <div className="space-y-4">
          {data.map((a) => (
            <AssignmentCard key={a.id} assignment={a} />
          ))}
        </div>
      ) : (
        <EmptyState title="No active assignments" description="Check back once your faculty publishes an assignment." />
      )}
    </div>
  );
}

function AssignmentCard({ assignment }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [uploadError, setUploadError] = useState(null);
  const fileInput = useRef(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const alreadySubmitted = Boolean(assignment.my_submission_id);

  const uploadMutation = useMutation({
    mutationFn: (file) => submissionsApi.uploadSubmission(assignment.id, file, setProgress),
    onMutate: () => {
      setUploading(true);
      setUploadError(null);
      setProgress(0);
    },
    onSuccess: (submission) => {
      queryClient.invalidateQueries({ queryKey: ["assignments"] });
      queryClient.invalidateQueries({ queryKey: ["my-submissions"] });
      navigate(`/submissions/${submission.id}`);
    },
    onError: (err) => {
      const isAlreadySubmitted = err?.response?.status === 409;
      setUploadError(
        isAlreadySubmitted
          ? "You've already submitted for this assignment."
          : apiErrorMessage(err, "Upload failed. Please try a PDF or DOCX file under 25MB.")
      );
      if (isAlreadySubmitted) {
        // Someone else's tab/request beat us to it — refresh so this card
        // switches to the "already submitted" state instead of staying
        // stuck offering an upload button that will just 409 again.
        queryClient.invalidateQueries({ queryKey: ["assignments"] });
      }
    },
    onSettled: () => setUploading(false),
  });

  const handleFile = (e) => {
    const file = e.target.files?.[0];
    if (file) uploadMutation.mutate(file);
    e.target.value = "";
  };

  // The progress bar tracks bytes sent over the wire, which reaches 100% the
  // moment the file finishes transferring — well before the server is done
  // extracting text and generating embeddings. Without this distinction the
  // button reads "Uploading… 100%" for the entire (often much longer)
  // processing time, which looks stuck even when it isn't.
  const buttonLabel = !uploading
    ? alreadySubmitted
      ? "Already submitted"
      : "Upload submission"
    : progress < 100
    ? `Uploading… ${progress}%`
    : "Processing…";

  return (
    <div className="card flex flex-col sm:flex-row sm:items-start justify-between gap-4 sm:gap-6">
      <div className="min-w-0">
        <h3 className="font-display text-lg text-ink">{assignment.title}</h3>
        {assignment.description && <p className="text-sm text-slate mt-1 max-w-xl">{assignment.description}</p>}
        {assignment.due_date && (
          <p className="text-xs font-mono text-slate-light mt-2">Due {new Date(assignment.due_date).toLocaleDateString()}</p>
        )}
        {uploadError && <p className="text-xs text-rust mt-2">{uploadError}</p>}
      </div>
      <div className="shrink-0 sm:text-right">
        <input ref={fileInput} type="file" accept=".pdf,.docx" className="hidden" onChange={handleFile} />
        {alreadySubmitted && !uploading ? (
          <button className="btn-secondary" onClick={() => navigate(`/submissions/${assignment.my_submission_id}`)}>
            View your submission
          </button>
        ) : (
          <button
            className="btn-primary"
            onClick={() => fileInput.current?.click()}
            disabled={uploading}
          >
            {buttonLabel}
          </button>
        )}
        <p className="text-[11px] text-slate-light mt-1.5">
          {alreadySubmitted && !uploading ? "One submission per assignment" : "PDF or DOCX, up to 25MB"}
        </p>
      </div>
    </div>
  );
}
