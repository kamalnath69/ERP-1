import React, { useMemo, useState, useEffect } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
  House, Users, GraduationCap, ChalkboardTeacher, CalendarBlank, Exam,
  Buildings, ShieldCheck, ChatCircleDots, ChartLineUp, CreditCard,
  Gear, SignOut, ClipboardText, Sparkle, ListChecks, UsersThree, Clock,
  CalendarDots, Bank, Books, Bus, Bed, Briefcase, FilePdf, Bell, UserPlus,
  Link as LinkIcon, CaretDown, CaretRight, UserCircle,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// -----------------------------------------------------------------------------
// Navigation config: grouped into collapsible sections.
// -----------------------------------------------------------------------------
const NAV_SECTIONS = [
  {
    id: "main",
    label: null, // no header for the "home" section
    items: [{ to: "/app", label: "Overview", icon: House, end: true }],
  },
  {
    id: "people",
    label: "People",
    items: [
      { to: "/app/students", label: "Students", icon: GraduationCap, perm: "students.view" },
      { to: "/app/parents", label: "Parents", icon: UsersThree, perm: "students.view" },
      { to: "/app/faculty", label: "Faculty", icon: ChalkboardTeacher, perm: "faculty.view" },
      { to: "/app/users", label: "Users", icon: Users, perm: "users.view" },
      { to: "/app/admissions", label: "Admissions", icon: UserPlus, perm: "students.view" },
    ],
  },
  {
    id: "academics",
    label: "Academics",
    items: [
      { to: "/app/academic", label: "Structure", icon: Buildings, perm: "academic.view" },
      { to: "/app/assignments", label: "Assignments", icon: LinkIcon, perm: "academic.view" },
      { to: "/app/timetable", label: "Timetable", icon: Clock, perm: "academic.view" },
      { to: "/app/calendar", label: "Calendar", icon: CalendarDots, perm: "academic.view" },
      { to: "/app/attendance", label: "Attendance", icon: CalendarBlank, perm: "attendance.view" },
      { to: "/app/marks", label: "Exams & Marks", icon: Exam, perm: "marks.view" },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    items: [
      { to: "/app/fees", label: "Fees", icon: Bank, perm: "billing.view" },
      { to: "/app/library", label: "Library", icon: Books, perm: "students.view" },
      { to: "/app/transport", label: "Transport", icon: Bus, perm: "students.view" },
      { to: "/app/hostel", label: "Hostel", icon: Bed, perm: "students.view" },
      { to: "/app/placements", label: "Placements", icon: Briefcase, perm: "students.view" },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { to: "/app/ai", label: "Athena AI", icon: Sparkle, perm: "ai.use" },
      { to: "/app/analytics", label: "Analytics", icon: ChartLineUp, perm: "analytics.view" },
      { to: "/app/reports", label: "Reports", icon: FilePdf, perm: "reports.view" },
    ],
  },
  {
    id: "system",
    label: "System",
    items: [
      { to: "/app/roles", label: "Roles & Permissions", icon: ShieldCheck, perm: "roles.manage" },
      { to: "/app/notifications", label: "Notifications", icon: Bell, perm: "notifications.view" },
      { to: "/app/audit", label: "Audit Logs", icon: ClipboardText, perm: "audit.view" },
      { to: "/app/billing", label: "Billing", icon: CreditCard, perm: "billing.view" },
      { to: "/app/settings", label: "Settings", icon: Gear, perm: "settings.manage" },
    ],
  },
];

const STORAGE_KEY = "athena.sidebar.sections.v1";

function useCollapsibleSections() {
  const [openSections, setOpenSections] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch {}
    // Default: only current-page's section expanded — approximate by opening People + Academics initially.
    return { people: true, academics: true, operations: false, intelligence: true, system: false };
  });

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(openSections)); } catch {}
  }, [openSections]);

  const toggle = (id) => setOpenSections((prev) => ({ ...prev, [id]: !prev[id] }));
  return { openSections, toggle };
}

export default function AppLayout({ children }) {
  const { user, organization, logout, can } = useAuth();
  const nav = useNavigate();
  const { openSections, toggle } = useCollapsibleSections();

  const visibleSections = useMemo(() => {
    return NAV_SECTIONS.map((sec) => ({
      ...sec,
      items: sec.items.filter((it) => !it.perm || can(it.perm)),
    })).filter((sec) => sec.items.length > 0);
  }, [can, user]);

  return (
    <div className="h-screen flex bg-background text-foreground overflow-hidden">
      <aside
        className="w-60 shrink-0 border-r border-border bg-secondary/30 flex flex-col h-screen"
        data-testid="app-sidebar"
      >
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

        <nav className="flex-1 overflow-y-auto py-2">
          {user?.is_super_admin && (
            <NavLink
              to="/super"
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2 text-sm hover:bg-secondary/70 ${
                  isActive ? "bg-accent/10 border-l-2 border-accent" : "border-l-2 border-transparent"
                }`
              }
              data-testid="nav-super-admin"
            >
              <ShieldCheck size={16} weight="bold" />
              <span>Super Admin</span>
            </NavLink>
          )}

          {visibleSections.map((section) => {
            // "main" section has no header — always visible.
            if (!section.label) {
              return (
                <div key={section.id}>
                  {section.items.map((it) => (
                    <SidebarLink key={it.to} item={it} />
                  ))}
                </div>
              );
            }

            const isOpen = !!openSections[section.id];
            const hasActive = section.items.some(
              (it) => typeof window !== "undefined" && window.location.pathname.startsWith(it.to)
            );

            return (
              <div key={section.id} className="mt-1">
                <button
                  type="button"
                  onClick={() => toggle(section.id)}
                  className={`w-full flex items-center justify-between px-5 pt-3 pb-1 text-[10px] uppercase tracking-widest transition-colors ${
                    hasActive ? "text-foreground" : "text-muted-foreground"
                  } hover:text-foreground`}
                  data-testid={`sidebar-section-${section.id}`}
                  aria-expanded={isOpen}
                >
                  <span>{section.label}</span>
                  {isOpen ? <CaretDown size={12} weight="bold" /> : <CaretRight size={12} weight="bold" />}
                </button>
                {isOpen && (
                  <div>
                    {section.items.map((it) => (
                      <SidebarLink key={it.to} item={it} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="p-3 border-t border-border">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="w-full flex items-center gap-3 p-2 hover:bg-secondary rounded-sm" data-testid="user-menu-trigger">
                <Avatar className="h-8 w-8 rounded-sm">
                  {user?.avatar_base64 ? (
                    <AvatarImage src={user.avatar_base64} alt={user?.first_name || "user"} />
                  ) : null}
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
              <DropdownMenuItem onClick={() => nav("/app/me")} data-testid="menu-profile">
                <UserCircle size={14} className="mr-2" /> My Profile
              </DropdownMenuItem>
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

      <div className="flex-1 flex flex-col min-w-0 h-screen">
        <header className="h-14 border-b border-border flex items-center justify-between px-6 bg-background shrink-0" data-testid="app-topbar">
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

function SidebarLink({ item }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      data-testid={`nav-${item.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
      className={({ isActive }) =>
        `flex items-center gap-3 px-5 py-2 text-sm transition-colors hover:bg-secondary ${
          isActive
            ? "bg-secondary text-foreground border-l-2 border-accent"
            : "text-muted-foreground border-l-2 border-transparent"
        }`
      }
    >
      <Icon size={16} />
      <span>{item.label}</span>
    </NavLink>
  );
}
