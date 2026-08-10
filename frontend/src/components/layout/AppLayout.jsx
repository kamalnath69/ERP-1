import React, { useEffect, useMemo, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import {
  Bell, Books, Briefcase, CalendarBlank, CaretDoubleLeft, CaretDown, ClockCounterClockwise,
  Command, DotsThreeCircle, Gear, List, MagnifyingGlass, Package, Plus, Receipt,
  ShoppingCart, SignOut, Sparkle, Storefront, UserCircle, UserPlus, Wallet, X,
} from "@phosphor-icons/react";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import DataHealthBanner from "@/components/DataHealthBanner";
import RealtimeSync from "@/components/RealtimeSync";
import AIQuickLauncher from "@/components/ai/AIQuickLauncher";
import { EntityAvatar, EntityProfileLink } from "@/components/entities/EntityProfile";
import { profileRef } from "@/lib/profileNavigation";
import { useGetQuery } from "@/store/api/baseApi";
import { useGetNotificationSummaryQuery } from "@/features/notifications/notificationsApi";
import { QUERY_POLICIES, withSkip } from "@/store/api/queryPolicies";
import { selectSidebarCompact, setSidebarCompact } from "@/store/slices/preferencesSlice";
import { clientLabel, routeForPath, routeLabel, visibleRoutes } from "@/app/routeManifest";
import { cn } from "@/lib/utils";

const RECENT_KEY = "edvatiq.command.recent";
export const PRIMARY_SIDEBAR_WIDTH_CLASS = "w-[232px]";

export default function AppLayout({ children }) {
  const dispatch = useDispatch();
  const compact = useSelector(selectSidebarCompact);
  const { user, organization: authOrg, can, logout } = useAuth();
  const { organization, locations, locationId, setLocationId, hasModule, wallet, entitlements } = useBusiness();
  const org = organization || authOrg;
  const current = useLocation();
  const navigate = useNavigate();
  const wide = useWideLayout();
  const rail = compact || !wide;
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [commandOpen, setCommandOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);

  const routes = useMemo(() => visibleRoutes({ industry: org?.industry, can, hasModule }), [can, hasModule, org?.industry]);
  const primary = routes.filter((route) => route.group === "primary");
  const secondary = routes.filter((route) => route.group === "more");
  const admin = routes.filter((route) => route.group === "admin");
  const currentRoute = routeForPath(current.pathname, org?.industry);
  const title = currentRoute ? routeLabel(currentRoute, org?.industry) : "Edvatiq";
  const secondaryWorkspace = currentRoute?.layout?.startsWith("secondary");
  const fixedSecondaryWorkspace = currentRoute?.layout === "secondary-fixed";
  const activeSecondary = currentRoute?.group === "more";
  const industryRoute = primary.find((route) => route.industries?.includes(org?.industry));
  const mobileRoutes = [
    primary.find((route) => route.key === "home"),
    primary.find((route) => route.key === "clients"),
    primary.find((route) => route.key === "calendar"),
    industryRoute || primary.find((route) => route.key === "sales"),
  ].filter(Boolean);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 180);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    setSearch("");
    setCommandOpen(false);
    setMobileMoreOpen(false);
  }, [current.pathname]);
  useEffect(() => { document.title = `${title} | Edvatiq`; }, [title]);
  useEffect(() => { if (activeSecondary) setMoreOpen(true); }, [activeSecondary]);
  useEffect(() => {
    const openCommand = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", openCommand);
    return () => window.removeEventListener("keydown", openCommand);
  }, []);

  const searchQuery = useGetQuery(
    { url: "/search", params: { q: debouncedSearch } },
    { skip: user?.is_super_admin || !commandOpen || debouncedSearch.length < 2 },
  );
  const notificationsQuery = useGetNotificationSummaryQuery(undefined, withSkip(QUERY_POLICIES.live, user?.is_super_admin));
  const results = debouncedSearch.length >= 2 ? searchQuery.data?.data || null : null;
  const unread = notificationsQuery.data?.unread || 0;
  if (user?.is_super_admin) return children;

  const closeCommand = () => { setSearch(""); setCommandOpen(false); };
  return <div className="flex h-screen overflow-hidden bg-background text-foreground">
    <RealtimeSync />
    <aside className={cn(
      "relative hidden shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200 md:flex",
      rail ? "w-[72px]" : PRIMARY_SIDEBAR_WIDTH_CLASS,
    )}>
      <Brand compact={rail} industry={org?.industry} />
      <nav aria-label="Main navigation" className="premium-scrollbar flex-1 overflow-y-auto px-2.5 py-3">
        <div className="space-y-1">{primary.map((route) => <NavItem key={route.key} route={route} compact={rail} industry={org?.industry} />)}</div>
        {!!secondary.length && <Collapsible open={moreOpen} onOpenChange={setMoreOpen} className="mt-1">
          <CollapsibleTrigger className={cn("nav-item nav-item-idle w-full", rail ? "justify-center px-0" : "gap-3", activeSecondary && "bg-secondary text-sidebar-foreground")} title={rail ? "More" : undefined}>
            <DotsThreeCircle size={19} weight="duotone" />{!rail && <><span className="flex-1 text-left">More</span><CaretDown size={13} className={cn("transition-transform", moreOpen && "rotate-180")} /></>}
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-1 space-y-1">{secondary.map((route) => <NavItem key={route.key} route={route} compact={rail} industry={org?.industry} subdued />)}</CollapsibleContent>
        </Collapsible>}
        {!!admin.length && <div className="mt-6 space-y-1">
          {!rail && <div className="px-3 pb-2 text-[9px] font-bold uppercase tracking-[0.16em] text-sidebar-muted/70">Administration</div>}
          {admin.map((route) => <NavItem key={route.key} route={route} compact={rail} industry={org?.industry} />)}
        </div>}
      </nav>
      {wide && <button onClick={() => dispatch(setSidebarCompact(!compact))} aria-label={compact ? "Expand navigation" : "Collapse navigation"} className="absolute -right-3 top-[5.2rem] z-10 grid h-7 w-7 place-items-center rounded-full border bg-card text-foreground shadow-sm transition-colors hover:bg-secondary">
        <CaretDoubleLeft size={13} className={cn("transition-transform", compact && "rotate-180")} />
      </button>}
      {can("ai.use") && hasModule("ai") && <SidebarWalletCard wallet={wallet} plan={entitlements?.plan} compact={rail} canManage={can("billing.view")} />}
      <SidebarAccount compact={rail} user={user} org={org} navigate={navigate} logout={logout} />
    </aside>

    <div className="flex h-screen min-w-0 flex-1 flex-col">
      <header className="relative z-40 flex h-16 shrink-0 items-center gap-2 border-b bg-card/90 px-3 backdrop-blur-xl sm:gap-3 md:px-5 lg:px-6">
        <div className="md:hidden"><Brand compact mobile industry={org?.industry} /></div>
        <div className="hidden min-w-0 flex-1 md:block">
          <div className="truncate text-sm font-semibold">{title}</div>
          <div className="mt-0.5 truncate text-[10px] text-muted-foreground">{org?.name}</div>
        </div>
        <button type="button" onClick={() => setCommandOpen(true)} className="group flex h-10 min-w-0 flex-1 items-center gap-2 rounded-xl border bg-surface-subtle px-3 text-left text-sm text-muted-foreground transition-colors hover:border-foreground/15 hover:bg-card md:max-w-xl md:flex-none lg:max-w-2xl">
          <MagnifyingGlass size={17} className="shrink-0" />
          <span className="truncate">{org?.industry === "college" ? "Search students and faculty" : "Search across your business"}</span>
          <span className="command-key ml-auto"><Command size={11} />K</span>
        </button>
        {locations.length > 1 && <Select value={locationId || ""} onValueChange={setLocationId}><SelectTrigger aria-label="Current location" className="hidden h-10 w-40 rounded-xl xl:flex"><Storefront size={16} /><SelectValue /></SelectTrigger><SelectContent>{locations.map((location) => <SelectItem value={location.id} key={location.id}>{location.name}</SelectItem>)}</SelectContent></Select>}
        <QuickCreate can={can} industry={org?.industry} navigate={navigate} />
        <button onClick={() => navigate("/app/notifications")} aria-label="Notifications" className="relative grid h-10 w-10 shrink-0 place-items-center rounded-xl border bg-card text-muted-foreground shadow-sm transition-colors hover:bg-secondary hover:text-foreground"><Bell size={18} />{unread > 0 && <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold text-accent-foreground">{unread > 99 ? "99+" : unread}</span>}</button>
        {can("ai.use") && hasModule("ai") && <Button onClick={() => setAiOpen(true)} className="hidden gap-2 lg:flex"><Sparkle weight="fill" /><span>Ask Edvatiq</span></Button>}
        <TopAccount user={user} org={org} navigate={navigate} logout={logout} />
      </header>
      <main id="main-content" className={cn(
        "premium-scrollbar flex-1",
        secondaryWorkspace
          ? cn("flex min-h-0 flex-col p-0 pb-[4.25rem] md:pb-0", fixedSecondaryWorkspace ? "overflow-hidden" : "overflow-y-auto")
          : "overflow-y-auto px-4 pb-28 pt-5 sm:px-5 md:px-6 md:pb-7 md:pt-6 lg:px-8",
      )}>
        {secondaryWorkspace ? <>
          <DataHealthBanner className="mx-4 mb-0 mt-4 shrink-0 sm:mx-5 md:mx-6 lg:mx-8" />
          <div className={cn("min-h-0 flex-1", fixedSecondaryWorkspace && "overflow-hidden")}>{children}</div>
        </> : <><DataHealthBanner />{children}</>}
      </main>
      <MobileNavigation
        routes={mobileRoutes}
        moreOpen={mobileMoreOpen}
        setMoreOpen={setMobileMoreOpen}
        industry={org?.industry}
        secondary={[...primary, ...secondary, ...admin]}
        locations={locations}
        locationId={locationId}
        setLocationId={setLocationId}
      />
      <AIQuickLauncher open={aiOpen} onOpenChange={setAiOpen} />
      <CommandPalette
        open={commandOpen}
        onOpenChange={setCommandOpen}
        search={search}
        setSearch={setSearch}
        results={results || { clients: [], employees: [], catalog: [] }}
        loading={searchQuery.isFetching}
        routes={routes}
        industry={org?.industry}
        can={can}
        navigate={navigate}
        close={closeCommand}
      />
    </div>
  </div>;
}

function useWideLayout() {
  const [wide, setWide] = useState(() => typeof window === "undefined" || window.matchMedia("(min-width: 1280px)").matches);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1280px)");
    const update = () => setWide(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  return wide;
}

function Brand({ compact = false, mobile = false, industry }) {
  return <Link to="/app" aria-label="Edvatiq home" className={cn("flex items-center overflow-hidden", mobile ? "w-10" : "h-16 border-b px-4", compact && !mobile && "justify-center px-0")}>
    <span className="relative grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-xl bg-primary text-sm font-bold text-primary-foreground shadow-sm">
      E<span className="absolute -bottom-2 -right-2 h-5 w-5 rounded-full bg-accent" />
    </span>
    {!compact && !mobile && <span className="ml-3 min-w-0"><span className="block truncate text-lg font-bold tracking-[-0.04em]">Edvatiq</span><span className="block text-[9px] font-semibold uppercase tracking-[0.16em] text-sidebar-muted">{industry === "college" ? "Placement OS" : "Business OS"}</span></span>}
  </Link>;
}

function NavItem({ route, compact, industry, subdued = false, onClick }) {
  const Icon = route.icon;
  const label = routeLabel(route, industry);
  return <NavLink to={route.path} end={route.end} title={compact ? label : undefined} onClick={onClick} className={({ isActive }) => cn("nav-item", compact ? "justify-center px-0" : "gap-3", isActive ? "nav-item-active" : "nav-item-idle", subdued && !isActive && "text-sidebar-muted/85")}><Icon size={19} weight="duotone" className="shrink-0" />{!compact && <span className="truncate">{label}</span>}</NavLink>;
}

function QuickCreate({ can, industry, navigate }) {
  const actions = creationActions(can, industry);
  if (!actions.length) return null;
  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <Button variant="outline" className="hidden h-10 gap-2 rounded-xl border-foreground/10 bg-card px-3.5 font-semibold shadow-sm lg:flex">
        <span className="grid h-6 w-6 place-items-center rounded-lg bg-primary text-primary-foreground"><Plus size={14} weight="bold" /></span>
        New
        <CaretDown size={13} className="text-muted-foreground" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-72 rounded-2xl p-2">
      <DropdownMenuLabel className="px-2 py-2">
        <span className="block text-sm font-semibold">Create new</span>
        <span className="mt-0.5 block text-[11px] font-normal text-muted-foreground">{industry === "college" ? "Add to the placement workspace" : "Start a business record"}</span>
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      {actions.map(([name, path]) => {
        const meta = createActionMeta(path, industry);
        const Icon = meta.icon;
        return <DropdownMenuItem key={path} onClick={() => navigate(path)} className="cursor-pointer gap-3 rounded-xl p-2.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-secondary text-muted-foreground"><Icon size={18} weight="duotone" /></span>
          <span className="min-w-0"><span className="block text-sm font-semibold text-foreground">{name}</span><span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{meta.description}</span></span>
        </DropdownMenuItem>;
      })}
    </DropdownMenuContent>
  </DropdownMenu>;
}

function createActionMeta(path, industry) {
  if (path.startsWith("/app/college")) {
    if (path.includes("section=students")) return { icon: UserPlus, description: "Create a complete academic admission" };
    if (path.includes("section=placements") && path.includes("new=company")) return { icon: Briefcase, description: "Add a placement partner" };
    if (path.includes("section=placements")) return { icon: Briefcase, description: "Create an opportunity and eligibility rules" };
    if (path.includes("section=imports")) return { icon: Books, description: "Validate and import student evidence" };
    return { icon: Books, description: "Add academic structure or a course" };
  }
  if (path.startsWith("/app/clients")) return { icon: UserPlus, description: industry === "clinic" ? "Register a patient profile" : industry === "college" ? "Admit a student profile" : "Add a client profile" };
  if (path.startsWith("/app/calendar")) return { icon: CalendarBlank, description: industry === "clinic" ? "Schedule a patient visit" : industry === "college" ? "Schedule student support" : "Schedule time with a client" };
  if (path.startsWith("/app/sales")) return { icon: ShoppingCart, description: "Create an invoice and collect payment" };
  return { icon: Package, description: "Add a product or service" };
}

function creationActions(can, industry) {
  if (industry === "college") return [
    can("college.students.manage") && ["Admit student", "/app/college?section=students&new=1"],
    can("college.opportunities.manage") && ["Placement drive", "/app/college?section=placements&new=drive"],
    can("college.companies.manage") && ["Placement company", "/app/college?section=placements&new=company"],
    can("college.imports.manage") && ["Import student data", "/app/college?section=imports"],
  ].filter(Boolean);
  return [
    can("clients.manage") && [clientLabel(industry, false), "/app/clients?new=1"],
    can("appointments.manage") && [industry === "clinic" ? "Appointment" : "Booking", "/app/calendar?new=1"],
    can("sales.manage") && ["Sale", "/app/sales?new=1"],
    can("catalog.manage") && ["Catalog item", "/app/catalog?new=1"],
  ].filter(Boolean);
}

function TopAccount({ user, org, navigate, logout }) {
  return <DropdownMenu><DropdownMenuTrigger asChild><button aria-label="Account menu" className="hidden rounded-full sm:block"><Avatar className="h-10 w-10 border shadow-sm"><AvatarImage src={user?.avatar_base64} /><AvatarFallback>{user?.first_name?.[0]}</AvatarFallback></Avatar></button></DropdownMenuTrigger><AccountMenu user={user} org={org} navigate={navigate} logout={logout} /></DropdownMenu>;
}

function SidebarAccount({ compact, user, org, navigate, logout }) {
  return <div className="border-t p-2.5"><DropdownMenu><DropdownMenuTrigger asChild><button className={cn("flex w-full items-center rounded-xl p-2 text-left transition-colors hover:bg-secondary", compact ? "justify-center" : "gap-3")}><Avatar className="h-9 w-9 border"><AvatarImage src={user?.avatar_base64} /><AvatarFallback className="bg-primary text-primary-foreground">{user?.first_name?.[0]}</AvatarFallback></Avatar>{!compact && <span className="min-w-0"><span className="block truncate text-sm font-semibold">{user?.first_name} {user?.last_name}</span><span className="block truncate text-[10px] text-sidebar-muted">{user?.designation || user?.email}</span></span>}</button></DropdownMenuTrigger><AccountMenu user={user} org={org} navigate={navigate} logout={logout} side="right" /></DropdownMenu></div>;
}

function AccountMenu({ user, org, navigate, logout, side }) {
  return <DropdownMenuContent side={side} align="end" className="w-64"><DropdownMenuLabel><div>{user?.first_name} {user?.last_name}</div><div className="mt-1 truncate text-xs font-normal text-muted-foreground">{org?.name}</div></DropdownMenuLabel><DropdownMenuSeparator /><DropdownMenuItem onClick={() => navigate("/app/me")}><UserCircle className="mr-2" />My profile</DropdownMenuItem><DropdownMenuItem onClick={() => navigate("/app/settings")}><Gear className="mr-2" />Settings</DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuItem onClick={async () => { await logout(); navigate("/login"); }}><SignOut className="mr-2" />Log out</DropdownMenuItem></DropdownMenuContent>;
}

function MobileNavigation({ routes, moreOpen, setMoreOpen, industry, secondary, locations, locationId, setLocationId }) {
  const uniqueMore = secondary.filter((route, index, all) => !routes.some((item) => item.key === route.key) && all.findIndex((item) => item.key === route.key) === index);
  return <>
    <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t bg-card/96 px-1 pb-[max(.4rem,env(safe-area-inset-bottom))] pt-1 backdrop-blur-xl md:hidden">
      {routes.map((route) => { const Icon = route.icon; const label = routeLabel(route, industry); return <NavLink key={route.key} to={route.path} end={route.end} className={({ isActive }) => cn("flex min-w-0 flex-col items-center gap-1 rounded-xl px-1 py-1.5 text-[9px] font-semibold", isActive ? "text-primary" : "text-muted-foreground")}><span className={cn("grid h-7 w-9 place-items-center rounded-lg", "group-[.active]:bg-primary/10")}><Icon size={19} weight="duotone" /></span><span className="max-w-full truncate">{label}</span></NavLink>; })}
      <button onClick={() => setMoreOpen(true)} className="flex flex-col items-center gap-1 rounded-xl px-1 py-1.5 text-[9px] font-semibold text-muted-foreground"><span className="grid h-7 w-9 place-items-center"><List size={19} /></span><span>More</span></button>
    </nav>
    <Sheet open={moreOpen} onOpenChange={setMoreOpen}>
      <SheetContent side="bottom" className="max-h-[86vh] rounded-t-3xl p-0 md:hidden">
        <SheetHeader className="border-b px-5 py-4 text-left"><SheetTitle className="text-xl font-semibold">Workspace</SheetTitle></SheetHeader>
        <div className="premium-scrollbar max-h-[72vh] overflow-y-auto p-4">
          {locations.length > 1 && <div className="mb-4"><div className="overline mb-2">Location</div><Select value={locationId || ""} onValueChange={setLocationId}><SelectTrigger className="w-full"><Storefront /><SelectValue /></SelectTrigger><SelectContent>{locations.map((location) => <SelectItem key={location.id} value={location.id}>{location.name}</SelectItem>)}</SelectContent></Select></div>}
          <nav className="grid grid-cols-2 gap-2" aria-label="More destinations">
            {uniqueMore.map((route) => { const Icon = route.icon; return <NavLink key={route.key} to={route.path} onClick={() => setMoreOpen(false)} className={({ isActive }) => cn("flex min-h-20 flex-col justify-between rounded-2xl border bg-card p-3.5 text-sm font-semibold", isActive && "border-primary bg-primary/5")}><Icon size={21} weight="duotone" /><span className="mt-3">{routeLabel(route, industry)}</span></NavLink>; })}
            <NavLink to="/app/me" onClick={() => setMoreOpen(false)} className="flex min-h-20 flex-col justify-between rounded-2xl border bg-card p-3.5 text-sm font-semibold"><UserCircle size={21} weight="duotone" /><span className="mt-3">My profile</span></NavLink>
          </nav>
        </div>
      </SheetContent>
    </Sheet>
  </>;
}

function CommandPalette({ open, onOpenChange, search, setSearch, results, loading, routes, industry, can, navigate, close }) {
  const recent = readRecent();
  const actions = creationActions(can, industry);
  const hasQuery = search.trim().length >= 2;
  return <Dialog open={open} onOpenChange={(value) => { onOpenChange(value); if (!value) setSearch(""); }}>
    <DialogContent className="top-[12vh] max-h-[76vh] max-w-2xl translate-y-0 overflow-hidden p-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2">
      <DialogTitle className="sr-only">Search and navigate</DialogTitle>
      <div className="flex h-14 items-center gap-3 border-b px-4"><MagnifyingGlass className="shrink-0 text-muted-foreground" size={20} /><input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder={industry === "college" ? "Search students and faculty..." : `Search ${clientLabel(industry).toLowerCase()}, team, catalog...`} className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />{search && <button onClick={() => setSearch("")} className="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground hover:bg-secondary"><X /></button>}<span className="command-key">ESC</span></div>
      <div className="premium-scrollbar max-h-[calc(76vh-3.5rem)] overflow-y-auto p-2">
        {hasQuery ? <SearchResultContent results={results} close={close} loading={loading} industry={industry} /> : <>
          {!!recent.length && <CommandGroup label="Recent"><div className="space-y-0.5">{recent.map((item) => <EntityProfileLink key={`${item.kind}:${item.id}`} profileRef={profileRef(item.kind, item.id)} onClick={close} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-secondary"><EntityAvatar name={item.name} kind={item.kind} avatarUrl={item.avatarUrl} className="h-9 w-9 rounded-lg text-xs" /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{item.name}</span><span className="block truncate text-xs text-muted-foreground">{item.meta || "Open profile"}</span></span><ClockCounterClockwise className="text-muted-foreground" /></EntityProfileLink>)}</div></CommandGroup>}
          <CommandGroup label="Navigate"><div className="grid gap-1 sm:grid-cols-2">{routes.filter((route) => route.group !== "hidden").map((route) => { const Icon = route.icon; return <button key={route.key} onClick={() => { navigate(route.path); close(); }} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold hover:bg-secondary"><span className="grid h-8 w-8 place-items-center rounded-lg bg-secondary"><Icon size={17} weight="duotone" /></span>{routeLabel(route, industry)}</button>; })}</div></CommandGroup>
          {!!actions.length && <CommandGroup label="Quick create"><div className="grid gap-1 sm:grid-cols-2">{actions.map(([label, path]) => <button key={path} onClick={() => { navigate(path); close(); }} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold hover:bg-secondary"><span className="grid h-8 w-8 place-items-center rounded-lg bg-accent/10 text-accent"><Plus /></span>{label}</button>)}</div></CommandGroup>}
        </>}
      </div>
    </DialogContent>
  </Dialog>;
}

function CommandGroup({ label, children }) {
  return <section className="p-2"><div className="px-2 pb-2 text-[9px] font-bold uppercase tracking-[0.16em] text-muted-foreground">{label}</div>{children}</section>;
}

export function SidebarWalletCard({ wallet, plan, compact, canManage }) {
  const available = Math.max(Number(wallet?.balance_credits ?? wallet?.available_credits ?? 0), 0);
  const included = Math.max(Number(wallet?.cycle_grant_credits || 0), 0);
  const scale = Math.max(included, available, 1);
  const percent = Math.min(100, Math.round((available / scale) * 100));
  const low = available === 0 || (included > 0 && available / included <= 0.2);
  const cycleDate = wallet?.cycle_end ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(wallet.cycle_end)) : null;
  const isTrial = plan?.slug === "trial" || ["trialing", "expired"].includes(plan?.subscription_status);
  const cycleLabel = !cycleDate ? null : isTrial ? plan?.subscription_status === "expired" ? `Ended ${cycleDate}` : `Expires ${cycleDate}` : `Renews ${cycleDate}`;
  const title = `${available.toLocaleString("en-IN")} AI credits available`;
  if (compact) {
    const content = <span className="relative grid h-10 w-10 place-items-center rounded-xl border bg-secondary text-sidebar-muted transition-colors hover:text-sidebar-foreground"><Wallet size={18} /><span className={cn("absolute right-1.5 top-1.5 h-2 w-2 rounded-full ring-2 ring-sidebar", low ? "bg-warning" : "bg-positive")} /></span>;
    return <div className="px-4 pb-2" title={title}>{canManage ? <Link to="/app/billing" aria-label={title}>{content}</Link> : content}</div>;
  }
  return <section className="mx-2.5 mb-2.5 overflow-hidden rounded-xl border bg-surface-subtle p-3" aria-label="AI credit wallet"><div className="flex items-center justify-between gap-2"><div className="flex min-w-0 items-center gap-2"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground"><Wallet size={16} weight="fill" /></span><div className="min-w-0"><div className="text-[9px] font-bold uppercase tracking-[0.13em] text-sidebar-muted">AI credits</div><div className="truncate text-xs font-semibold">{available.toLocaleString("en-IN")} available</div></div></div>{canManage && <Link to="/app/billing" className="shrink-0 text-[10px] font-semibold text-accent">Plan</Link>}</div><div className="mt-2.5 h-1 overflow-hidden rounded-full bg-border"><div className={cn("h-full rounded-full transition-[width]", low ? "bg-warning" : "bg-positive")} style={{ width: `${percent}%` }} /></div>{cycleLabel && <div className="mt-1.5 truncate text-[9px] text-sidebar-muted">{cycleLabel}</div>}</section>;
}

export function SearchResults({ results, close, loading = false, industry = "gym" }) {
  return <div className="absolute inset-x-0 top-full z-[100] mt-2 max-h-[min(30rem,72vh)] overflow-y-auto rounded-2xl border bg-card p-2 shadow-2xl premium-scrollbar"><SearchResultContent results={results} close={close} loading={loading} industry={industry} /></div>;
}

function SearchResultContent({ results, close, loading = false, industry = "gym" }) {
  const groups = industry === "college"
    ? [["Students", results.clients, "client"], ["Faculty & staff", results.employees, "employee"]]
    : [[clientLabel(industry), results.clients, "client"], ["Team", results.employees, "employee"], ["Catalog", results.catalog, "catalog"]];
  const hasResults = groups.some(([, items]) => items?.length);
  if (loading && !hasResults) return <div className="space-y-2 p-2" aria-label="Searching"><div className="h-14 animate-pulse rounded-xl bg-secondary" /><div className="h-14 animate-pulse rounded-xl bg-secondary" /><div className="h-14 animate-pulse rounded-xl bg-secondary" /></div>;
  if (!hasResults) return <div className="p-8 text-center text-sm text-muted-foreground">{industry === "college" ? "No matching students or faculty members." : `No matching ${clientLabel(industry).toLowerCase()}, employees, or catalog items.`}</div>;
  return groups.map(([label, items, kind]) => items?.length ? <div key={label}><div className="px-3 py-2 text-[9px] font-bold uppercase tracking-[0.16em] text-muted-foreground">{label}</div>{items.map((item) => {
    const name = item.display_name || item.name || `${item.first_name} ${item.last_name}`;
    const meta = item.display_meta || item.phone || item.designation || item.sku || "Open profile";
    return <EntityProfileLink key={item.id} profileRef={profileRef(kind, item.id)} onClick={() => { rememberRecent({ kind, id: item.id, name, meta, avatarUrl: item.avatar_url }); close(); }} ariaLabel={`Open ${name} profile`} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><EntityAvatar name={name} kind={kind} avatarUrl={item.avatar_url} className="h-10 w-10 rounded-xl text-sm" /><span className="min-w-0 flex-1"><span className="block truncate font-semibold">{name}</span><span className="mt-0.5 block truncate text-xs text-muted-foreground">{meta}</span></span>{(item.status || typeof item.is_active === "boolean") && <span className="status-badge status-neutral shrink-0">{item.status || (item.is_active ? "active" : "inactive")}</span>}</EntityProfileLink>;
  })}</div> : null);
}

function readRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]").slice(0, 5); } catch { return []; }
}

function rememberRecent(item) {
  try {
    const current = readRecent().filter((row) => row.kind !== item.kind || row.id !== item.id);
    localStorage.setItem(RECENT_KEY, JSON.stringify([item, ...current].slice(0, 5)));
  } catch {}
}
