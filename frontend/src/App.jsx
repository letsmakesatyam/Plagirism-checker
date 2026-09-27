import { Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import NotFound from "./pages/NotFound";
import { useAuth } from "./context/AuthContext";

import FacultyDashboard from "./pages/faculty/FacultyDashboard";
import Assignments from "./pages/faculty/Assignments";
import AssignmentDetail from "./pages/faculty/AssignmentDetail";
import ReportsSearch from "./pages/faculty/ReportsSearch";
import InternetSources from "./pages/faculty/InternetSources";
import Comparison from "./pages/faculty/Comparison";

import StudentDashboard from "./pages/student/StudentDashboard";
import StudentAssignments from "./pages/student/StudentAssignments";
import MySubmissions from "./pages/student/MySubmissions";

import SubmissionReport from "./pages/shared/SubmissionReport";

function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "faculty" ? "/faculty/dashboard" : "/student/dashboard"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/submissions/:id" element={<SubmissionReport />} />

          <Route element={<ProtectedRoute role="faculty" />}>
            <Route path="/faculty/dashboard" element={<FacultyDashboard />} />
            <Route path="/faculty/assignments" element={<Assignments />} />
            <Route path="/faculty/assignments/:id" element={<AssignmentDetail />} />
            <Route path="/faculty/reports" element={<ReportsSearch />} />
            <Route path="/faculty/sources" element={<InternetSources />} />
            <Route path="/faculty/compare/:aId/:bId" element={<Comparison />} />
          </Route>

          <Route element={<ProtectedRoute role="student" />}>
            <Route path="/student/dashboard" element={<StudentDashboard />} />
            <Route path="/student/assignments" element={<StudentAssignments />} />
            <Route path="/student/submissions" element={<MySubmissions />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
