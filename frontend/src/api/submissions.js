import client from "./client";

export const uploadSubmission = (assignmentId, file, onProgress) => {
  const form = new FormData();
  form.append("file", file);
  return client
    .post(`/assignments/${assignmentId}/submissions`, form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (evt) => {
        if (onProgress && evt.total) onProgress(Math.round((evt.loaded / evt.total) * 100));
      },
    })
    .then((r) => r.data);
};

export const listMySubmissions = (params = {}) =>
  client.get("/submissions/mine", { params }).then((r) => r.data);

export const getSubmission = (id) => client.get(`/submissions/${id}`).then((r) => r.data);

export const listAssignmentSubmissions = (assignmentId, params = {}) =>
  client.get(`/assignments/${assignmentId}/submissions`, { params }).then((r) => r.data);

export const getSimilarParagraphs = (id, topK = 5) =>
  client.get(`/submissions/${id}/similar-paragraphs`, { params: { top_k: topK } }).then((r) => r.data);

export const getDocumentView = (id) =>
  client.get(`/submissions/${id}/document-view`).then((r) => r.data);

export const getPageImageBlob = (id, page, annotated = false) =>
  client
    .get(`/submissions/${id}/pages/${page}/image`, {
      params: { annotated },
      responseType: "blob",
    })
    .then((r) => r.data);

export const downloadAnnotatedDocument = (id) =>
  client
    .get(`/submissions/${id}/annotated-file`, { responseType: "blob" })
    .then((r) => r.data);

export const downloadOriginalFile = (id) =>
  client
    .get(`/submissions/${id}/file`, { responseType: "blob" })
    .then((r) => r.data);
