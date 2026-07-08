import React from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
  House, Users, GraduationCap, ChalkboardTeacher, CalendarBlank, Exam,
  Buildings, ShieldCheck, ChatCircleDots, ChartLineUp, CreditCard,
  Gear, SignOut, ClipboardText, Sparkle, ListChecks, UsersThree, Clock,
  CalendarDots, Bank, Books, Bus, Bed, Briefcase, FilePdf, Bell, UserPlus, Link as LinkIcon,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

const NAV = [
  { to: "/app", label: "Overview", icon: House, perm: null, end: true },
  { section: "People" },
  { to: "/app/students", label: "Students", icon: GraduationCap, perm: "students.view" },
  { to: "/app/parents", label: "Parents", icon: UsersThree, perm: "students.view" },
  { to: "/app/faculty", label: "Faculty", icon: ChalkboardTeacher, perm: "faculty.view" },
  { to: "/app/users", label: "Users", icon: Users, perm: "users.view" },
  { to: "/app/admissions", label: "Admissions", icon: UserPlus, perm: "students.view" },
  { section: "Academics" },
  { to: "/app/academic", label: "Structure", icon: Buildings, perm: "academic.view" },
  { to: "/app/assignments", label: "Assignments", icon: LinkIcon, perm: "academic.view" },
  { to: "/app/timetable", label: "Timetable", icon: Clock, perm: "academic.view" },
  { to: "/app/calendar", label: "Calendar", icon: CalendarDots, perm: "academic.view" },
  { to: "/app/attendance", label: "Attendance", icon: CalendarBlank, perm: "attendance.view" },
  { to: "/app/marks", label: "Exams & Marks", icon: Exam, perm: "marks.view" },
  { section: "Operations" },
  { to: "/app/fees", label: "Fees", icon: Bank, perm: "billing.view" },
  { to: "/app/library", label: "Library", icon: Books, perm: "students.view" },
  { to: "/app/transport", label: "Transport", icon: Bus, perm: "students.view" },
  { to: "/app/hostel", label: "Hostel", icon: Bed, perm: "students.view" },
  { to: "/app/placements", label: "Placements", icon: Briefcase, perm: "students.view" },
  { section: "Intelligence" },
  { to: "/app/ai", label: "Athena AI", icon: Sparkle, perm: "ai.use" },
  { to: "/app/analytics", label: "Analytics", icon: ChartLineUp, perm: "analytics.view" },
  { to: "/app/reports", label: "Reports", icon: FilePdf, perm: "reports.view" },
  { section: "System" },
  { to: "/app/roles", label: "Roles & Permissions", icon: ShieldCheck, perm: "roles.manage" },
  { to: "/app/notifications", label: "Notifications", icon: Bell, perm: "notifications.view" },
  { to: "/app/audit", label: "Audit Logs", icon: ClipboardText, perm: "audit.view" },
  { to: "/app/billing", label: "Billing", icon: CreditCard, perm: "billing.view" },
  { to: "/app/settings", label: "Settings", icon: Gear, perm: "settings.manage" },
];

export default function AppLayout({ children }) {
  const { user, organization, logout, can } = useAuth();
  const nav = useNavigate();

  return (
    <div className="h-screen flex bg-background text-foreground overflow-hidden">
      <aside className="w-60 shrink-0 border-r border-border bg-secondary/30 flex flex-col h-screen sticky top-0" data-testid="app-sidebar">
        <Link to="/app" className="p-5 border-b border-border block">
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-display font-bold tracking-tight">Athena</span>
            <span className="text-[10px] overline">ERP</span>
          </div>
          <div className="mt-3">
            <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Organization</div>
            <div className="text-sm font-medium truncate" data-testid="tenant-name">
              {organization?.name || (user?.is_super_admin ? "Platform" : "—")}
            </div>
          </div>
        </Link>
        <nav className="flex-1 overflow-y-auto py-3">
          {user?.is_super_admin && (
            <NavLink to="/super" className={({ isActive }) => `flex items-center gap-3 px-5 py-2 text-sm hover:bg-secondary/70 ${isActive ? "bg-accent/10 border-l-2 border-accent" : ""}`} data-testid="nav-super-admin">
              <ShieldCheck size={16} weight="bold" />
              <span>Super Admin</span>
            </NavLink>
          )}
          {NAV.map((n, idx) => {
            if (n.section) {
              return (
                <div key={`section-${idx}`} className="px-5 pt-4 pb-1 overline text-[10px]">
                  {n.section}
                </div>
              );
            }
            if (n.perm && !can(n.perm)) return null;
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                data-testid={`nav-${n.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-5 py-2 text-sm transition-colors hover:bg-secondary ${
                    isActive ? "bg-secondary text-foreground border-l-2 border-accent" : "text-muted-foreground border-l-2 border-transparent"
                  }`
                }
              >
                <Icon size={16} />
                <span>{n.label}</span>
              </NavLink>
            );
          })}
        </nav>
        <div className="p-3 border-t border-border">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="w-full flex items-center gap-3 p-2 hover:bg-secondary rounded-sm" data-testid="user-menu-trigger">
                <Avatar className="h-8 w-8 rounded-sm">
                  <AvatarFallback className="rounded-sm bg-primary text-primary-foreground text-xs">
                    {(user?.first_name?.[0] || "?") + (user?.last_name?.[0] || "")}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 text-left overflow-hidden">
                  <div className="text-sm truncate">{user?.first_name} {user?.last_name}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{user?.email}</div>
                </div>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>Signed in</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => nav("/app/settings")} data-testid="menu-settings">
                <Gear size={14} className="mr-2" /> Settings
              </DropdownMenuItem>
              <DropdownMenuItem onClick={async () => { await logout(); nav("/login"); }} data-testid="menu-logout">
                <SignOut size={14} className="mr-2" /> Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-border flex items-center justify-between px-6 bg-background" data-testid="app-topbar">
          <div className="flex items-center gap-3">
            <span className="overline">Athena / {organization?.name || "Platform"}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs px-2 py-1 border border-border rounded-sm font-mono uppercase tracking-widest" data-testid="plan-badge">
              {organization?.plan || (user?.is_super_admin ? "platform" : "trial")}
            </span>
            <Button variant="outline" size="sm" className="rounded-sm" onClick={() => nav("/app/ai")} data-testid="topbar-ai-btn">
              <ChatCircleDots size={14} className="mr-2" /> Ask Athena
            </Button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6" data-testid="app-main">{children}</main>
      </div>
    </div>
  );
}
