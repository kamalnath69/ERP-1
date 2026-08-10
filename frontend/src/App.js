import React, { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { BusinessProvider, useBusiness } from "@/contexts/BusinessContext";
import { Toaster } from "@/components/ui/sonner";
import AppLayout from "@/components/layout/AppLayout";
import RouteGate from "@/components/routing/RouteGate";
import { NotFoundPage } from "@/pages/SystemPages";
import { PageSkeleton } from "@/components/system";

const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const Register = lazy(() => import("@/pages/Register"));
const VerifyEmail = lazy(() => import("@/pages/VerifyEmail"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));
const PlatformInvite = lazy(() => import("@/pages/PlatformInvite"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Clients = lazy(() => import("@/pages/Clients"));
const ClientProfile = lazy(() => import("@/pages/ClientProfile"));
const CalendarPage = lazy(() => import("@/pages/Calendar"));
const Sales = lazy(() => import("@/pages/Sales"));
const Catalog = lazy(() => import("@/pages/Catalog"));
const CatalogProfile = lazy(() => import("@/pages/CatalogProfile"));
const Inventory = lazy(() => import("@/pages/Inventory"));
const Gym = lazy(() => import("@/pages/Gym"));
const Salon = lazy(() => import("@/pages/Salon"));
const Clinic = lazy(() => import("@/pages/Clinic"));
const College = lazy(() => import("@/pages/CollegeWorkspace"));
const AIChat = lazy(() => import("@/pages/AIChat"));
const Team = lazy(() => import("@/pages/Team"));
const EmployeeProfile = lazy(() => import("@/pages/EmployeeProfile"));
const AccessControl = lazy(() => import("@/pages/AccessControl"));
const Reports = lazy(() => import("@/pages/Reports"));
const Billing = lazy(() => import("@/pages/Billing"));
const Settings = lazy(() => import("@/pages/Settings"));
const MyProfile = lazy(() => import("@/pages/MyProfile"));
const Notifications = lazy(() => import("@/pages/Notifications"));
const Documents = lazy(() => import("@/pages/Documents"));
const SuperAdmin = lazy(() => import("@/pages/SuperAdmin"));

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="grid min-h-screen place-items-center bg-background"><div className="h-10 w-10 animate-spin rounded-full border-2 border-primary/20 border-t-primary" /></div>;
  return user ? children : <Navigate to="/login" replace />;
}

function TrialAccess({ children }) {
  const { entitlements, loading } = useBusiness();
  const location = useLocation();
  const expired = entitlements?.plan?.subscription_status === "expired";
  const allowed = ["/app/billing", "/app/me", "/app/notifications"].some((path) => location.pathname.startsWith(path));
  if (loading && !entitlements) return <PageSkeleton />;
  if (expired && !allowed) return <Navigate to="/app/billing" replace state={{ trialExpired: true }} />;
  return children;
}

function SecurityEnrollment({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user?.mfa_enrollment_required && location.pathname !== "/app/me") {
    return <Navigate to="/app/me?tab=security" replace />;
  }
  return children;
}

function ProtectedAppShell() {
  return <RequireAuth><SecurityEnrollment><TrialAccess><AppLayout><Suspense fallback={<PageSkeleton />}><Outlet /></Suspense></AppLayout></TrialAccess></SecurityEnrollment></RequireAuth>;
}

const gated = (key, element) => <RouteGate routeKey={key}>{element}</RouteGate>;
const protectedPage = (Page) => <RequireAuth><Suspense fallback={<PageSkeleton />}><Page /></Suspense></RequireAuth>;

export default function App() {
  return <AuthProvider><BusinessProvider><BrowserRouter><Toaster richColors closeButton position="top-right" /><Suspense fallback={<PageSkeleton className="p-6" />}><Routes>
    <Route path="/" element={<Landing />} />
    <Route path="/login" element={<Login />} />
    <Route path="/register" element={<Register />} />
    <Route path="/verify-email" element={<VerifyEmail />} />
    <Route path="/forgot-password" element={<ForgotPassword />} />
    <Route path="/platform-invite" element={<PlatformInvite />} />
    <Route path="/super/*" element={protectedPage(SuperAdmin)} />
    <Route element={<ProtectedAppShell />}>
      <Route path="/app" element={gated("home", <Dashboard />)} />
      <Route path="/app/clients" element={gated("clients", <Clients />)} />
      <Route path="/app/clients/:clientId" element={gated("clients", <ClientProfile />)} />
      <Route path="/app/calendar" element={gated("calendar", <CalendarPage />)} />
      <Route path="/app/sales" element={gated("sales", <Sales />)} />
      <Route path="/app/sales/:invoiceId" element={gated("sales", <Sales />)} />
      <Route path="/app/catalog" element={gated("catalog", <Catalog />)} />
      <Route path="/app/catalog/:itemId" element={gated("catalog", <CatalogProfile />)} />
      <Route path="/app/inventory" element={gated("inventory", <Inventory />)} />
      <Route path="/app/gym/*" element={gated("gym", <Gym />)} />
      <Route path="/app/salon/*" element={gated("salon", <Salon />)} />
      <Route path="/app/clinic/*" element={gated("clinic", <Clinic />)} />
      <Route path="/app/college/*" element={gated("college", <College />)} />
      <Route path="/app/ai" element={gated("ai", <AIChat />)} />
      <Route path="/app/team" element={gated("team", <Team />)} />
      <Route path="/app/team/:employeeId" element={gated("team", <EmployeeProfile />)} />
      <Route path="/app/access" element={gated("access", <AccessControl />)} />
      <Route path="/app/reports" element={gated("reports", <Reports />)} />
      <Route path="/app/billing" element={gated("billing", <Billing />)} />
      <Route path="/app/settings" element={gated("settings", <Settings />)} />
      <Route path="/app/me" element={gated("profile", <MyProfile />)} />
      <Route path="/app/notifications" element={gated("notifications", <Notifications />)} />
      <Route path="/app/documents" element={gated("documents", <Documents />)} />
      <Route path="/app/*" element={<NotFoundPage embedded />} />
    </Route>
    <Route path="*" element={<NotFoundPage />} />
  </Routes></Suspense></BrowserRouter></BusinessProvider></AuthProvider>;
}
