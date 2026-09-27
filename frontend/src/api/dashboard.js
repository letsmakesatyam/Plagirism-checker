import client from "./client";

export const facultyDashboard = () => client.get("/faculty/dashboard").then((r) => r.data);
export const studentDashboard = () => client.get("/students/dashboard").then((r) => r.data);
