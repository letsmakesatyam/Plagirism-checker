import client from "./client";

export const generateReport = (submissionId) =>
  client.post(`/submissions/${submissionId}/generate-report`).then((r) => r.data);
export const getReport = (submissionId) =>
  client.get(`/submissions/${submissionId}/report`).then((r) => r.data);
export const downloadReportPdf = (submissionId) =>
  client.get(`/submissions/${submissionId}/report/pdf`, { responseType: "blob" }).then((r) => r.data);
export const listReports = (params = {}) => client.get("/reports", { params }).then((r) => r.data);
export const compareSubmissions = (a, b) =>
  client.get(`/submissions/${a}/compare/${b}`).then((r) => r.data);
