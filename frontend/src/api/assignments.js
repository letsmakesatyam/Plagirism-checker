import client from "./client";

export const listAssignments = (params = {}) =>
  client.get("/assignments", { params }).then((r) => r.data);
export const getAssignment = (id) => client.get(`/assignments/${id}`).then((r) => r.data);
export const createAssignment = (payload) => client.post("/assignments", payload).then((r) => r.data);
export const updateAssignment = (id, payload) => client.put(`/assignments/${id}`, payload).then((r) => r.data);
export const deleteAssignment = (id) => client.delete(`/assignments/${id}`).then((r) => r.data);
