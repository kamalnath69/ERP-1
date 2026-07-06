import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";

import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import Students from "@/pages/Students";
import StudentProfile from "@/pages/StudentProfile";
import Faculty from "@/pages/Faculty";
import Attendance from "@/pages/Attendance";
import Marks from "@/pages/Marks";
import Roles from "@/pages/Roles";
import Academic from "@/pages/Academic";
import AIChat from "@/pages/AIChat";
import Analytics from "@/pages/Analytics";
import Billing from "@/pages/Billing";
import SuperAdmin from "@/pages/SuperAdmin";
import Users from "@/pages/Users";
import AuditLogs from "@/pages/AuditLogs";
import SettingsPage from "@/pages/Settings";
import AppLayout from "@/components/layout/AppLayout";

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster richColors closeButton position="top-right" />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          <Route path="/super" element={<RequireAuth><AppLayout><SuperAdmin /></AppLayout></RequireAuth>} />

          <Route path="/app" element={<RequireAuth><AppLayout><Dashboard /></AppLayout></RequireAuth>} />
          <Route path="/app/students" element={<RequireAuth><AppLayout><Students /></AppLayout></RequireAuth>} />
          <Route path="/app/students/:id" element={<RequireAuth><AppLayout><StudentProfile /></AppLayout></RequireAuth>} />
          <Route path="/app/faculty" element={<RequireAuth><AppLayout><Faculty /></AppLayout></RequireAuth>} />
          <Route path="/app/attendance" element={<RequireAuth><AppLayout><Attendance /></AppLayout></RequireAuth>} />
          <Route path="/app/marks" element={<RequireAuth><AppLayout><Marks /></AppLayout></RequireAuth>} />
          <Route path="/app/roles" element={<RequireAuth><AppLayout><Roles /></AppLayout></RequireAuth>} />
          <Route path="/app/academic" element={<RequireAuth><AppLayout><Academic /></AppLayout></RequireAuth>} />
          <Route path="/app/ai" element={<RequireAuth><AppLayout><AIChat /></AppLayout></RequireAuth>} />
          <Route path="/app/analytics" element={<RequireAuth><AppLayout><Analytics /></AppLayout></RequireAuth>} />
          <Route path="/app/billing" element={<RequireAuth><AppLayout><Billing /></AppLayout></RequireAuth>} />
          <Route path="/app/users" element={<RequireAuth><AppLayout><Users /></AppLayout></RequireAuth>} />
          <Route path="/app/audit" element={<RequireAuth><AppLayout><AuditLogs /></AppLayout></RequireAuth>} />
          <Route path="/app/settings" element={<RequireAuth><AppLayout><SettingsPage /></AppLayout></RequireAuth>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
