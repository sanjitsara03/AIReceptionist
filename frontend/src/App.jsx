import { useState, useEffect } from 'react';
import { Auth0Provider, useAuth0 } from '@auth0/auth0-react';
import { I } from './icons.jsx';
import { DataProvider, useData } from './DataContext.jsx';
import { LoginPage } from './components/LoginPage.jsx';
import { Sidebar, TopBar } from './components/Shell.jsx';
import { TweaksPanel, TweakSection, TweakRadio, useTweaks } from './components/TweaksPanel.jsx';
import { TodayView } from './views/TodayView.jsx';
import { JobsView, JobDrawer } from './views/JobsView.jsx';
import { ConversationsView } from './views/ConversationsView.jsx';
import { CustomersView } from './views/CustomersView.jsx';
import { SettingsView } from './views/SettingsView.jsx';
import { AdminApp } from './admin/AdminApp.jsx';

const AUTH0_DOMAIN   = import.meta.env.VITE_AUTH0_DOMAIN;
const AUTH0_CLIENT   = import.meta.env.VITE_AUTH0_CLIENT_ID;
const AUTH0_AUDIENCE = import.meta.env.VITE_AUTH0_AUDIENCE;

const ACCENT_OPTIONS = {
  blue:    { hue: 250, name: "Blue" },
  emerald: { hue: 155, name: "Emerald" },
  violet:  { hue: 295, name: "Violet" },
  amber:   { hue: 60,  name: "Amber" },
  rose:    { hue: 15,  name: "Rose" },
};

const TWEAK_DEFAULTS = {
  accent:  "blue",
  theme:   "light",
  density: "comfortable",
};

function applyDesignTokens(t) {
  const hue = ACCENT_OPTIONS[t.accent]?.hue ?? 250;
  document.documentElement.style.setProperty("--accent", `oklch(0.55 0.15 ${hue})`);
  document.documentElement.style.setProperty("--accent-hover", `oklch(0.50 0.16 ${hue})`);
  document.documentElement.style.setProperty(
    "--accent-soft",
    t.theme === "dark" ? `oklch(0.30 0.06 ${hue})` : `oklch(0.95 0.04 ${hue})`
  );
  document.documentElement.setAttribute("data-theme", t.theme);
  document.documentElement.setAttribute("data-density", t.density);
}

export default function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  useEffect(() => { applyDesignTokens(t); }, [t]);

  // The /admin route uses a totally separate auth model (X-Admin-Secret in
  // localStorage, no Auth0). Branch BEFORE Auth0Provider so the admin app
  // doesn't pay the Auth0 init cost or interfere with admin sessions.
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/admin")) {
    return <AdminApp />;
  }

  return (
    <Auth0Provider
      domain={AUTH0_DOMAIN}
      clientId={AUTH0_CLIENT}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: AUTH0_AUDIENCE,
      }}
      onRedirectCallback={(appState) => {
        if (appState?.inviteToken) {
          sessionStorage.setItem("pendingInviteToken", appState.inviteToken);
        }
        window.history.replaceState({}, document.title, appState?.returnTo ?? "/");
      }}
    >
      <AuthGate t={t} setTweak={setTweak} />
    </Auth0Provider>
  );
}

function AuthGate({ t, setTweak }) {
  const { isAuthenticated, isLoading, error } = useAuth0();

  if (error) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100vh", background: "var(--bg)", gap: 12 }}>
        <div style={{ color: "var(--error, #e53e3e)", fontWeight: 600 }}>Auth0 error</div>
        <div style={{ fontSize: 13, color: "var(--text-subtle)", fontFamily: "monospace", maxWidth: 480, textAlign: "center" }}>{error.message}</div>
        <button className="btn" onClick={() => window.location.replace("/")}>Try again</button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "var(--bg)" }}>
        <span style={{ color: "var(--text-subtle)", fontSize: 13 }}>Loading…</span>
      </div>
    );
  }

  if (!isAuthenticated) return <LoginPage />;

  return (
    <DataProvider>
      <DataGuard t={t} setTweak={setTweak} />
    </DataProvider>
  );
}

function DataGuard({ t, setTweak }) {
  const { loading, noBusiness, loadError } = useData();
  const { logout } = useAuth0();

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "var(--bg)" }}>
        <span style={{ color: "var(--text-subtle)", fontSize: 13 }}>Loading…</span>
      </div>
    );
  }

  if (loadError) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100vh", background: "var(--bg)", gap: 14 }}>
        <div style={{ fontWeight: 600, fontSize: 16, color: "var(--error, #e53e3e)" }}>Couldn't load your data</div>
        <div style={{ fontSize: 13, color: "var(--text-subtle)", fontFamily: "monospace", maxWidth: 480, textAlign: "center" }}>{loadError}</div>
        <button className="btn" onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }

  if (noBusiness) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100vh", background: "var(--bg)", gap: 14 }}>
        <div style={{ fontWeight: 600, fontSize: 16 }}>No business linked</div>
        <div style={{ fontSize: 13, color: "var(--text-subtle)", maxWidth: 360, textAlign: "center", lineHeight: 1.6 }}>
          This account isn't associated with any business. Contact your administrator to get access.
        </div>
        <button className="btn ghost" onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>
          Sign out
        </button>
      </div>
    );
  }

  return <AppShell t={t} setTweak={setTweak} />;
}

function AppShell({ t, setTweak }) {
  const { data } = useData();
  const [view, setView] = useState("today");
  const [drawerJobId, setDrawerJobId] = useState(null);

  const bizName = data.business?.name ?? "Dashboard";
  const counts = {
    jobs: data.jobs?.length ?? null,
    conversations: data.conversations?.length ?? null,
    customers: data.customers?.length ?? null,
  };

  const titles = {
    today:         { title: "Today",         crumbs: [bizName, "Today"] },
    jobs:          { title: "Jobs",           crumbs: [bizName, "Jobs"] },
    conversations: { title: "Conversations", crumbs: [bizName, "Conversations"] },
    customers:     { title: "Customers",     crumbs: [bizName, "Customers"] },
    settings:      { title: "Settings",      crumbs: [bizName, "Settings"] },
  };

  return (
    <div className="app">
      <Sidebar
        active={view}
        onSelect={(v) => { setView(v); setDrawerJobId(null); }}
        business={data.business}
        counts={counts}
      />

      <div className="main">
        <TopBar {...titles[view]} liveCall={null} />

        <div className="content" data-screen-label={view}>
          {view === "today" && (
            <TodayView
              onOpenJob={(id) => { setView("jobs"); setDrawerJobId(id); }}
              onOpenConversation={() => setView("conversations")}
            />
          )}
          {view === "jobs" && <JobsView onOpenJob={setDrawerJobId} />}
          {view === "conversations" && <ConversationsView />}
          {view === "customers" && <CustomersView />}
          {view === "settings" && <SettingsView />}
        </div>
      </div>

      {drawerJobId && view === "jobs" && (
        <JobDrawer jobId={drawerJobId} onClose={() => setDrawerJobId(null)} />
      )}

      <TweaksPanel title="Tweaks">

        <TweakSection title="Theme">
          <TweakRadio
            label="Mode"
            value={t.theme}
            options={[
              { value: "light", label: "Light" },
              { value: "dark",  label: "Dark" },
            ]}
            onChange={(v) => setTweak("theme", v)}
          />
          <TweakRadio
            label="Density"
            value={t.density}
            options={[
              { value: "comfortable", label: "Comfortable" },
              { value: "compact",     label: "Compact" },
            ]}
            onChange={(v) => setTweak("density", v)}
          />
        </TweakSection>

        <TweakSection title="Accent">
          <AccentSwatches value={t.accent} onChange={(v) => setTweak("accent", v)} />
        </TweakSection>

        <TweakSection title="Demo">
          <div style={{ fontSize: 12, color: "var(--text-subtle)", lineHeight: 1.5 }}>
            All data is from <span className="mono">seed.py</span> — Joe's Plumbing, 3 technicians,
            and a synthetic Monday's worth of jobs and conversations.
          </div>
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

function AccentSwatches({ value, onChange }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
      {Object.entries(ACCENT_OPTIONS).map(([key, opt]) => {
        const isActive = value === key;
        return (
          <button
            key={key}
            onClick={() => onChange(key)}
            title={opt.name}
            style={{
              border: "1px solid " + (isActive ? "var(--text)" : "var(--border)"),
              borderRadius: 6,
              padding: 6,
              background: "var(--bg-elev)",
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
              gap: 5,
              alignItems: "stretch",
            }}
          >
            <div
              style={{
                height: 22,
                borderRadius: 4,
                background: `oklch(0.55 0.15 ${opt.hue})`,
                boxShadow: "inset 0 1px 0 oklch(1 0 0 / 0.2), inset 0 -1px 0 oklch(0 0 0 / 0.1)",
              }}
            />
            <div style={{ fontSize: 10, color: isActive ? "var(--text)" : "var(--text-subtle)", textAlign: "center", fontWeight: isActive ? 600 : 500 }}>
              {opt.name}
            </div>
          </button>
        );
      })}
    </div>
  );
}
