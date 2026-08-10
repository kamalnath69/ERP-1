import React, { useEffect, useMemo, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Bell, CheckCircle, Copy, Desktop, DeviceMobile, FloppyDisk, Key, LockKey,
  Moon, PaintBrush, ShieldCheck, SignOut, Sparkle, Sun, UserCircle,
} from "@phosphor-icons/react";
import { toast } from "sonner";

import { clientLabel } from "@/app/routeManifest";
import AvatarUploader from "@/components/AvatarUploader";
import AssistantPersonalizationSheet, { assistantPreferences } from "@/components/ai/AssistantPersonalizationSheet";
import PasswordStrength, { isPasswordAcceptable } from "@/components/PasswordStrength";
import { DetailHero, PageHeader, PageShell, StatusBadge, Surface } from "@/components/system";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/contexts/AuthContext";
import { useBusiness } from "@/contexts/BusinessContext";
import {
  useChangeMyPasswordMutation, useDisableMyMfaMutation, useGetMySecurityQuery,
  useGetMySessionsQuery, useRegenerateRecoveryCodesMutation, useRevokeAllMySessionsMutation,
  useRevokeMySessionMutation, useStartMyMfaMutation, useUpdateMyProfileMutation,
  useVerifyMyMfaMutation,
} from "@/features/account/accountApi";
import { useSaveMyPreferenceMutation } from "@/store/api/workspaceApi";
import { fetchMe, patchUser } from "@/store/slices/authSlice";
import {
  resetDashboardLayout, selectAppearance, setAppearance,
} from "@/store/slices/preferencesSlice";

const notificationDefaults = {
  work_assigned: true,
  appointments: true,
  payments: true,
  client_attention: true,
  product_updates: false,
};

export default function MyProfile() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { user, organization, roles, permissions, logout } = useAuth();
  const { context, locations } = useBusiness();
  const appearance = useSelector(selectAppearance);
  const [form, setForm] = useState({ first_name: "", last_name: "", phone: "", designation: "", bio: "", avatar_base64: null });
  const [password, setPassword] = useState({ current_password: "", new_password: "", confirm: "" });
  const [notifications, setNotifications] = useState(notificationDefaults);
  const [mfaDialog, setMfaDialog] = useState(null);
  const [mfaForm, setMfaForm] = useState({ current_password: "", code: "" });
  const [enrollment, setEnrollment] = useState(null);
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [personalizationOpen, setPersonalizationOpen] = useState(false);
  const assistant = assistantPreferences(context);
  const entityLabel = clientLabel(organization?.industry);
  const entitySingular = clientLabel(organization?.industry, false);
  const isCollege = organization?.industry === "college";

  const sessions = useGetMySessionsQuery();
  const security = useGetMySecurityQuery();
  const [updateProfile, profileState] = useUpdateMyProfileMutation();
  const [changePassword, passwordState] = useChangeMyPasswordMutation();
  const [revokeSession] = useRevokeMySessionMutation();
  const [revokeAll] = useRevokeAllMySessionsMutation();
  const [savePreference] = useSaveMyPreferenceMutation();
  const [startMfa, startMfaState] = useStartMyMfaMutation();
  const [verifyMfa, verifyMfaState] = useVerifyMyMfaMutation();
  const [regenerateCodes, regenerateState] = useRegenerateRecoveryCodesMutation();
  const [disableMfa, disableState] = useDisableMyMfaMutation();

  useEffect(() => {
    if (!user) return;
    setForm({
      first_name: user.first_name || "", last_name: user.last_name || "",
      phone: user.phone || "", designation: user.designation || "",
      bio: user.bio || "", avatar_base64: user.avatar_base64 || null,
    });
  }, [user]);
  useEffect(() => {
    const saved = context?.preferences?.notifications?.value;
    if (saved) setNotifications((current) => ({ ...current, ...saved }));
  }, [context?.preferences?.notifications]);
  useEffect(() => {
    if ((params.get("security") === "mfa" || user?.mfa_enrollment_required) && params.get("tab") !== "security") {
      setParams({ tab: "security" }, { replace: true });
    }
  }, [params, setParams, user?.mfa_enrollment_required]);

  const activeTab = params.get("tab") || "profile";
  const setTab = (tab) => setParams(tab === "profile" ? {} : { tab }, { replace: true });
  const initials = `${user?.first_name?.[0] || "?"}${user?.last_name?.[0] || ""}`;
  const permissionSummary = useMemo(() => summarizeAccess(permissions, entitySingular), [entitySingular, permissions]);

  const saveProfile = async () => {
    try {
      const result = await updateProfile(form).unwrap();
      dispatch(patchUser(result));
      dispatch(fetchMe());
      toast.success("Profile updated");
    } catch (error) { toast.error(error?.data?.detail || "Profile could not be updated"); }
  };
  const saveAppearance = async (mode) => {
    dispatch(setAppearance(mode));
    try { await savePreference({ namespace: "appearance", value: { mode } }).unwrap(); }
    catch { toast.error("Appearance could not be synced to your other devices"); }
  };
  const saveNotifications = async (next) => {
    setNotifications(next);
    try { await savePreference({ namespace: "notifications", value: next }).unwrap(); }
    catch { toast.error("Notification preferences could not be saved"); }
  };
  const submitPassword = async () => {
    if (password.new_password !== password.confirm) return toast.error("New passwords do not match");
    if (!isPasswordAcceptable(password.new_password)) return toast.error("Choose a stronger password");
    try {
      await changePassword({ current_password: password.current_password, new_password: password.new_password }).unwrap();
      toast.success("Password updated. Sign in again to continue");
      navigate("/login", { replace: true });
    } catch (error) { toast.error(error?.data?.detail || "Password could not be updated"); }
  };

  const beginEnrollment = async () => {
    try {
      const result = await startMfa({ current_password: mfaForm.current_password }).unwrap();
      setEnrollment(result);
      setMfaForm((current) => ({ ...current, code: "" }));
    } catch (error) { toast.error(error?.data?.detail || "Authenticator setup could not start"); }
  };
  const completeEnrollment = async () => {
    try {
      const result = await verifyMfa({ code: mfaForm.code }).unwrap();
      setRecoveryCodes(result.recovery_codes || []);
      setEnrollment(null);
      security.refetch();
      toast.success("Authenticator security enabled");
    } catch (error) { toast.error(error?.data?.detail || "The authenticator code was not accepted"); }
  };
  const finishEnrollment = async () => {
    await logout();
    navigate("/login", { replace: true, state: { email: user.email, workspace: organization?.slug } });
  };
  const sensitiveMfaAction = async () => {
    try {
      if (mfaDialog === "disable") {
        await disableMfa(mfaForm).unwrap();
        toast.success("Authenticator security disabled. Sign in again to continue");
        navigate("/login", { replace: true });
      } else {
        const result = await regenerateCodes(mfaForm).unwrap();
        setRecoveryCodes(result.recovery_codes || []);
        setMfaDialog("recovery");
        security.refetch();
      }
    } catch (error) { toast.error(error?.data?.detail || "Security settings could not be changed"); }
  };

  if (!user) return null;
  return <PageShell size="standard" className="reveal" data-testid="my-profile-page">
    <PageHeader eyebrow="Your account" title="My profile" description="Personal details, practical access, preferences, sessions, and account security in one place." />
    {user.mfa_enrollment_required && <Surface className="border-warning/40 bg-warning-soft p-5"><div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><ShieldCheck className="shrink-0 text-warning" size={24} /><div><div className="font-semibold">Authenticator setup is required</div><p className="mt-1 text-sm text-muted-foreground">Your organization requires an additional sign-in code for this account.</p></div></div><Button onClick={() => { setTab("security"); setMfaDialog("enroll"); }}>Set up now</Button></div></Surface>}

    <DetailHero
      avatar={<div className="h-20 w-20 overflow-hidden rounded-3xl bg-primary text-primary-foreground grid place-items-center font-display text-3xl">{form.avatar_base64 ? <img src={form.avatar_base64} alt="Your profile" className="h-full w-full object-cover" /> : initials}</div>}
      eyebrow={organization?.name || "Edvatiq"}
      title={`${user.first_name} ${user.last_name}`.trim()}
      subtitle={`${user.designation || (isCollege ? "Faculty or staff" : "Team member")} · ${user.email}`}
      badges={<><StatusBadge status={user.email_verified ? "active" : "warning"} label={user.email_verified ? "Email verified" : "Email verification needed"} />{roles.map((role) => <StatusBadge key={role.id || role.slug} status="neutral" label={role.name} />)}</>}
      metrics={[
        { label: "Roles", value: roles.length }, { label: isCollege ? "Campuses" : "Locations", value: locations.length },
        { label: "Responsibility areas", value: permissionSummary.length }, { label: "Signed-in devices", value: sessions.data?.length },
      ]}
    />

    <Tabs value={activeTab} onValueChange={setTab}>
      <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-2xl bg-surface-subtle p-1 premium-scrollbar">
        <Tab value="profile" icon={UserCircle}>Profile</Tab><Tab value="access" icon={ShieldCheck}>My access</Tab><Tab value="preferences" icon={PaintBrush}>Preferences</Tab><Tab value="security" icon={LockKey}>Security</Tab>
      </TabsList>

      {activeTab === "preferences" && <Surface className="mt-5 flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6"><div className="flex gap-4"><div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-primary text-primary-foreground"><Sparkle size={20} weight="fill" className="text-accent" /></div><div><div className="font-semibold">Edvatiq assistant</div><p className="mt-1 text-sm text-muted-foreground">{`${capitalize(assistant.tone)} tone, ${assistant.detail} answers${assistant.preferred_name ? `, calling you ${assistant.preferred_name}` : ""}.`}</p></div></div><Button variant="outline" onClick={() => setPersonalizationOpen(true)}>Personalize</Button></Surface>}

      <TabsContent value="profile" className="mt-5"><Surface className="p-5 sm:p-7"><SectionTitle title="Profile details" copy="These details help your team identify and contact you." /><div className="mt-6 space-y-6"><AvatarUploader value={form.avatar_base64} onChange={(value) => setForm((current) => ({ ...current, avatar_base64: value }))} initials={initials} /><div className="grid gap-4 sm:grid-cols-2"><Field label="First name"><Input data-testid="profile-first-name" value={form.first_name} onChange={field(setForm, "first_name")} /></Field><Field label="Last name"><Input value={form.last_name} onChange={field(setForm, "last_name")} /></Field><Field label="Phone"><Input data-testid="profile-phone" inputMode="tel" value={form.phone} onChange={field(setForm, "phone")} /></Field><Field label="Job title"><Input data-testid="profile-designation" value={form.designation} onChange={field(setForm, "designation")} placeholder={isCollege ? "Placement head, HOD, faculty..." : "Studio manager, senior trainer..."} /></Field></div><Field label="About me"><Textarea rows={4} data-testid="profile-bio" value={form.bio} onChange={field(setForm, "bio")} placeholder="A short introduction for your team" /></Field><div className="flex justify-end"><Button data-testid="profile-save-btn" disabled={profileState.isLoading} onClick={saveProfile}><FloppyDisk className="mr-2" />{profileState.isLoading ? "Saving..." : "Save profile"}</Button></div></div></Surface></TabsContent>

      <TabsContent value="access" className="mt-5 space-y-5"><div className="grid gap-5 lg:grid-cols-2"><Surface className="p-5 sm:p-6"><SectionTitle title="Responsibilities" copy="A readable summary of what your current roles allow." /><div className="mt-5 grid gap-3 sm:grid-cols-2">{permissionSummary.map((area) => <div className="rounded-2xl bg-surface-subtle p-4" key={area.name}><div className="font-semibold">{area.name}</div><div className="mt-1 text-xs text-muted-foreground">{area.level}</div></div>)}</div></Surface><Surface className="p-5 sm:p-6"><SectionTitle title="Where I work" copy={isCollege ? "Your data is limited to these campuses and assignments." : "Your data is limited to these operating locations and assignments."} /><div className="mt-5 space-y-3">{locations.map((location) => <div key={location.id} className="flex items-center justify-between rounded-2xl border p-4"><div><div className="font-semibold">{location.name}</div><div className="mt-1 text-xs text-muted-foreground">{location.city || location.code}</div></div>{location.is_primary && <StatusBadge status="active" label="Primary" />}</div>)}</div><p className="mt-5 text-xs leading-5 text-muted-foreground">Owners manage role, {isCollege ? "campus" : "location"}, and {entityLabel.toLowerCase()} reach from Access. Changes are recorded in the security history.</p></Surface></div></TabsContent>

      <TabsContent value="preferences" className="mt-5 space-y-5"><Surface className="p-5 sm:p-6"><SectionTitle title="Appearance" copy="Use one look everywhere, follow your device, or choose explicitly." /><div className="mt-5 grid gap-3 sm:grid-cols-3">{[["light", Sun, "Light"], ["dark", Moon, "Dark"], ["system", Desktop, "Use device setting"]].map(([mode, Icon, label]) => <button key={mode} type="button" onClick={() => saveAppearance(mode)} className={`rounded-2xl border p-5 text-left transition-colors ${appearance === mode ? "border-accent bg-accent/5 ring-2 ring-accent/15" : "hover:bg-surface-hover"}`}><Icon size={24} className="text-accent" /><div className="mt-4 font-semibold">{label}</div><div className="mt-1 text-xs text-muted-foreground">{mode === "system" ? "Changes with your device" : `Always use ${mode} mode`}</div></button>)}</div></Surface><Surface className="p-5 sm:p-6"><SectionTitle title="In-app notifications" copy="Choose what deserves your attention. Security notices cannot be turned off." /><div className="mt-5 divide-y">{Object.entries(notificationDefaults).map(([key]) => <PreferenceSwitch key={key} label={notificationLabel(key, entityLabel)} checked={notifications[key]} onChange={(checked) => saveNotifications({ ...notifications, [key]: checked })} />)}</div></Surface><Surface className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between"><div><div className="font-semibold">Dashboard layout</div><p className="mt-1 text-sm text-muted-foreground">Restore the role-aware Home dashboard to its recommended arrangement.</p></div><Button variant="outline" onClick={async () => { dispatch(resetDashboardLayout("default")); await savePreference({ namespace: "dashboard", value: { layouts: {} } }); toast.success("Dashboard layout restored"); }}>Restore default</Button></Surface></TabsContent>

      <TabsContent value="security" className="mt-5 space-y-5"><SecurityPanel state={security} onEnroll={() => { setMfaForm({ current_password: "", code: "" }); setEnrollment(null); setRecoveryCodes([]); setMfaDialog("enroll"); }} onCodes={() => { setMfaForm({ current_password: "", code: "" }); setMfaDialog("regenerate"); }} onDisable={() => { setMfaForm({ current_password: "", code: "" }); setMfaDialog("disable"); }} /><SessionsPanel query={sessions} revoke={async (session) => { try { const result = await revokeSession(session.id).unwrap(); if (result.signed_out) return navigate("/login", { replace: true }); toast.success("Device signed out"); } catch (error) { toast.error(error?.data?.detail || "Device could not be signed out"); } }} revokeAll={async () => { try { await revokeAll().unwrap(); navigate("/login", { replace: true }); } catch { toast.error("Sessions could not be closed"); } }} /><Surface className="p-5 sm:p-6"><SectionTitle title="Change password" copy="Changing your password closes every existing session." /><div className="mt-5 grid gap-4 md:grid-cols-3"><Field label="Current password"><Input data-testid="pw-current" type="password" autoComplete="current-password" value={password.current_password} onChange={field(setPassword, "current_password")} /></Field><Field label="New password"><Input data-testid="pw-new" type="password" autoComplete="new-password" value={password.new_password} onChange={field(setPassword, "new_password")} /><PasswordStrength password={password.new_password} compact /></Field><Field label="Confirm new password"><Input data-testid="pw-confirm" type="password" autoComplete="new-password" value={password.confirm} onChange={field(setPassword, "confirm")} /></Field></div><div className="mt-5 flex justify-end"><Button data-testid="pw-save-btn" variant="outline" disabled={passwordState.isLoading || !isPasswordAcceptable(password.new_password) || password.confirm !== password.new_password} onClick={submitPassword}>{passwordState.isLoading ? "Updating..." : "Update password"}</Button></div></Surface></TabsContent>
    </Tabs>

    <AssistantPersonalizationSheet open={personalizationOpen} onOpenChange={setPersonalizationOpen} />

    <Dialog open={Boolean(mfaDialog)} onOpenChange={(open) => { if (!open && !recoveryCodes.length) { setMfaDialog(null); setEnrollment(null); } }}><DialogContent className="sm:max-w-lg"><DialogHeader><DialogTitle className="font-display text-3xl">{mfaDialog === "disable" ? "Turn off authenticator security" : mfaDialog === "regenerate" ? "Replace recovery codes" : "Set up authenticator security"}</DialogTitle></DialogHeader>
      {recoveryCodes.length ? <RecoveryCodes codes={recoveryCodes} finish={mfaDialog === "enroll" ? finishEnrollment : () => { setRecoveryCodes([]); setMfaDialog(null); }} /> : mfaDialog === "enroll" ? !enrollment ? <div className="space-y-5"><p className="text-sm leading-6 text-muted-foreground">Confirm your password before connecting an authenticator app.</p><Field label="Current password"><Input autoFocus type="password" value={mfaForm.current_password} onChange={field(setMfaForm, "current_password")} /></Field><Button className="w-full" disabled={startMfaState.isLoading || !mfaForm.current_password} onClick={beginEnrollment}>{startMfaState.isLoading ? "Preparing..." : "Continue"}</Button></div> : <div className="space-y-5"><p className="text-sm leading-6 text-muted-foreground">Open your authenticator app, add an account using the setup key below, then enter its six-digit code.</p><div className="rounded-2xl border bg-surface-subtle p-4"><div className="text-xs text-muted-foreground">Setup key</div><div className="mt-2 break-all font-mono text-lg font-semibold tracking-wider">{enrollment.secret}</div><Button className="mt-3" size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(enrollment.secret)}><Copy className="mr-2" />Copy key</Button></div><a href={enrollment.provisioning_uri} className="block text-center text-sm font-semibold text-accent sm:hidden">Open authenticator app</a><Field label="6-digit code"><Input autoFocus inputMode="numeric" autoComplete="one-time-code" value={mfaForm.code} onChange={field(setMfaForm, "code")} /></Field><Button className="w-full" disabled={verifyMfaState.isLoading || mfaForm.code.length < 6} onClick={completeEnrollment}>{verifyMfaState.isLoading ? "Verifying..." : "Verify and enable"}</Button></div> : <div className="space-y-5"><p className="text-sm leading-6 text-muted-foreground">Confirm with your password and a current authenticator or recovery code.</p><Field label="Current password"><Input type="password" value={mfaForm.current_password} onChange={field(setMfaForm, "current_password")} /></Field><Field label="Authenticator or recovery code"><Input value={mfaForm.code} onChange={field(setMfaForm, "code")} /></Field><Button className="w-full" variant={mfaDialog === "disable" ? "destructive" : "default"} disabled={disableState.isLoading || regenerateState.isLoading || !mfaForm.current_password || mfaForm.code.length < 6} onClick={sensitiveMfaAction}>{disableState.isLoading || regenerateState.isLoading ? "Confirming..." : mfaDialog === "disable" ? "Turn off and sign out" : "Create new codes"}</Button></div>}
    </DialogContent></Dialog>
  </PageShell>;
}

function SecurityPanel({ state, onEnroll, onCodes, onDisable }) {
  const mfa = state.data?.mfa;
  return <Surface className="p-5 sm:p-6"><div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"><div className="flex gap-4"><div className={`grid h-12 w-12 shrink-0 place-items-center rounded-2xl ${mfa?.enabled ? "bg-positive-soft text-positive" : "bg-surface-subtle text-muted-foreground"}`}><ShieldCheck size={25} /></div><div><div className="flex flex-wrap items-center gap-2"><h2 className="font-display text-2xl font-semibold">Authenticator security</h2><StatusBadge status={mfa?.enabled ? "active" : mfa?.required ? "warning" : "neutral"} label={mfa?.enabled ? "Enabled" : mfa?.required ? "Required" : "Optional"} /></div><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">Use a changing code from an authenticator app when signing in. Recovery codes help if your device is unavailable.</p>{mfa?.enabled && <p className="mt-2 text-xs text-muted-foreground">{mfa.recovery_codes_remaining} unused recovery codes remain.</p>}</div></div><div className="flex shrink-0 flex-wrap gap-2">{mfa?.enabled ? <><Button variant="outline" onClick={onCodes}>New recovery codes</Button><Button variant="outline" disabled={mfa.required} title={mfa.required ? "Your organization requires this protection" : undefined} onClick={onDisable}>Turn off</Button></> : <Button onClick={onEnroll}>Set up authenticator</Button>}</div></div></Surface>;
}

function SessionsPanel({ query, revoke, revokeAll }) {
  return <Surface className="p-5 sm:p-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><SectionTitle title="Signed-in devices" copy="Close any session you do not recognize." /><Button variant="outline" onClick={revokeAll}>Sign out everywhere</Button></div><div className="mt-5 divide-y">{query.isLoading ? [1, 2].map((item) => <div key={item} className="h-20 animate-pulse bg-surface-subtle" />) : query.data?.length ? query.data.map((session) => <div key={session.id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3">{/mobile|android|iphone/i.test(session.user_agent || "") ? <DeviceMobile size={22} className="text-accent" /> : <Desktop size={22} className="text-accent" />}<div><div className="font-medium">{deviceName(session.user_agent)} {session.is_current && <StatusBadge className="ml-2" status="active" label="This device" />}</div><div className="mt-1 text-xs text-muted-foreground">Signed in {new Date(session.created_at).toLocaleString("en-IN")}</div></div></div><Button size="sm" variant="outline" onClick={() => revoke(session)}><SignOut className="mr-2" />Sign out</Button></div>) : <p className="text-sm text-muted-foreground">No other active devices.</p>}</div></Surface>;
}

function RecoveryCodes({ codes, finish }) {
  const all = codes.join("\n");
  return <div className="space-y-5"><div className="rounded-2xl border border-warning/30 bg-warning-soft p-4"><div className="font-semibold">Save these codes now</div><p className="mt-1 text-sm text-muted-foreground">Each code works once. They are not shown again after this dialog closes.</p></div><div className="grid grid-cols-2 gap-2 rounded-2xl bg-surface-subtle p-4">{codes.map((code) => <code key={code} className="rounded-lg bg-card px-3 py-2 text-center text-sm">{code}</code>)}</div><Button variant="outline" className="w-full" onClick={() => { navigator.clipboard.writeText(all); toast.success("Recovery codes copied"); }}><Copy className="mr-2" />Copy all codes</Button><Button className="w-full" onClick={finish}>I saved these codes</Button></div>;
}

function PreferenceSwitch({ label, checked, onChange }) { return <label className="flex cursor-pointer items-center justify-between gap-4 py-4"><span className="text-sm font-medium">{label}</span><input type="checkbox" className="h-5 w-5 accent-[hsl(var(--accent))]" checked={checked} onChange={(event) => onChange(event.target.checked)} /></label>; }
function Tab({ value, icon: Icon, children }) { return <TabsTrigger value={value} className="gap-2 rounded-xl"><Icon />{children}</TabsTrigger>; }
function SectionTitle({ title, copy }) { return <div><h2 className="font-display text-2xl font-semibold">{title}</h2>{copy && <p className="mt-1 text-sm leading-6 text-muted-foreground">{copy}</p>}</div>; }
function Field({ label, children }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div>; }
function field(setter, key) { return (event) => setter((current) => ({ ...current, [key]: event.target.value })); }
function notificationLabel(key, entityLabel) { const college = entityLabel === "Students"; return ({ work_assigned: "Work assigned to me", appointments: college ? "Student meeting and schedule changes" : "Appointment and schedule changes", payments: college ? "Internship fee-clearance updates" : "Payments and balances", client_attention: `${entityLabel} needing attention`, product_updates: "Edvatiq product updates" })[key]; }
function capitalize(value = "") { return value ? `${value[0].toUpperCase()}${value.slice(1)}` : ""; }
function summarizeAccess(codes = [], entityLabel = "Client") {
  const groups = new Map();
  codes.forEach((code) => {
    const [module, action = "view"] = code.split(".");
    if (["settings", "audit"].includes(module)) return;
    const current = groups.get(module) || new Set();
    current.add(action);
    groups.set(module, current);
  });
  return [...groups.entries()].map(([module, actions]) => ({ name: friendlyModule(module, entityLabel), level: [...actions].some((action) => /manage|write|record|adjust|mark|sign|send/.test(action)) ? "Can view and manage" : "Can view" })).slice(0, 12);
}
function friendlyModule(value, entityLabel) { const college = entityLabel === "Student"; return ({ clients: `${entityLabel} records`, clinical: "Clinical records", client_memory: `${entityLabel} context`, client_signals: `${entityLabel} attention`, gym: "Gym operations", college: "College placement", ai: "Edvatiq AI", employees: college ? "Faculty & staff" : "Team", appointments: college ? "Student schedule" : "Calendar" })[value] || value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function deviceName(agent = "") { if (/mobile|android|iphone/i.test(agent)) return "Mobile browser"; if (/edg/i.test(agent)) return "Microsoft Edge"; if (/chrome/i.test(agent)) return "Google Chrome"; if (/firefox/i.test(agent)) return "Firefox"; if (/safari/i.test(agent)) return "Safari"; return "Browser session"; }
