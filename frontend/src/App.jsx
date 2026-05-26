import { useState, useEffect } from 'react';
import { Auth0Provider, useAuth0 } from '@auth0/auth0-react';
import { DataProvider, useData } from './DataContext.jsx';
import { LoginPage } from './components/LoginPage.jsx';
import { Sidebar, TopBar } from './components/Shell.jsx';
import { TodayView } from './views/TodayView.jsx';
import { JobsView, JobDrawer } from './views/JobsView.jsx';
import { ConversationsView } from './views/ConversationsView.jsx';
import { CustomersView } from './views/CustomersView.jsx';
import { SettingsView } from './views/SettingsView.jsx';
import { AdminApp } from './admin/AdminApp.jsx';
import { SmsTerms } from './components/SmsTerms.jsx';

const AUTH0_DOMAIN   = import.meta.env.VITE_AUTH0_DOMAIN;
const AUTH0_CLIENT   = import.meta.env.VITE_AUTH0_CLIENT_ID;
const AUTH0_AUDIENCE = import.meta.env.VITE_AUTH0_AUDIENCE;

// Single hard-coded accent + theme — the dev-only TweaksPanel that used to
// switch these has been removed for production. CSS still keys off the
// --accent custom property and the data-theme/data-density attributes.
const ACCENT_HUE = 250; // blue

function applyDesignTokens() {
  document.documentElement.style.setProperty("--accent", `oklch(0.55 0.15 ${ACCENT_HUE})`);
  document.documentElement.style.setProperty("--accent-hover", `oklch(0.50 0.16 ${ACCENT_HUE})`);
  document.documentElement.style.setProperty("--accent-soft", `oklch(0.95 0.04 ${ACCENT_HUE})`);
  document.documentElement.setAttribute("data-theme", "light");
  document.documentElement.setAttribute("data-density", "comfortable");
}

export default function App() {
  useEffect(() => { applyDesignTokens(); }, []);

  // The /admin route uses a totally separate auth model (X-Admin-Secret in
  // localStorage, no Auth0). Branch BEFORE Auth0Provider so the admin app
  // doesn't pay the Auth0 init cost or interfere with admin sessions.
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/admin")) {
    return <AdminApp />;
  }

  // Public SMS terms / CTA page for Twilio toll-free verification. No auth,
  // no Auth0 init, no app shell — intentionally a static, unindexed page.
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/sms-terms")) {
    return <SmsTerms />;
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
      <AuthGate />
    </Auth0Provider>
  );
}

function AuthGate() {
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
      <DataGuard />
    </DataProvider>
  );
}

function DataGuard() {
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

  return <AppShell />;
}

function AppShell() {
  const { data } = useData();
  const [view, setView] = useState("today");
  const [drawerJobId, setDrawerJobId] = useState(null);
  const [creatingJob, setCreatingJob] = useState(false);
  const [focusedCustomerId, setFocusedCustomerId] = useState(null);
  const [focusedConversationId, setFocusedConversationId] = useState(null);

  const openJob = (id) => { setView("jobs"); setDrawerJobId(id); };
  const openCustomer = (id) => { setView("customers"); setFocusedCustomerId(id); };
  const openConversation = (id) => { setView("conversations"); setFocusedConversationId(id); };
  const startNewJob = () => { setView("jobs"); setCreatingJob(true); };

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
        <TopBar
          {...titles[view]}
          data={data}
          onNewJob={startNewJob}
          onOpenJob={openJob}
          onOpenCustomer={openCustomer}
          onOpenConversation={openConversation}
        />

        <div className="content" data-screen-label={view}>
          {view === "today" && (
            <TodayView
              onOpenJob={openJob}
              onOpenConversation={() => setView("conversations")}
            />
          )}
          {view === "jobs" && (
            <JobsView
              onOpenJob={setDrawerJobId}
              creating={creatingJob}
              onCloseCreate={() => setCreatingJob(false)}
            />
          )}
          {view === "conversations" && (
            <ConversationsView
              focusConversationId={focusedConversationId}
              onOpenCustomer={openCustomer}
            />
          )}
          {view === "customers" && (
            <CustomersView focusCustomerId={focusedCustomerId} />
          )}
          {view === "settings" && <SettingsView />}
        </div>
      </div>

      {drawerJobId && view === "jobs" && (
        <JobDrawer jobId={drawerJobId} onClose={() => setDrawerJobId(null)} />
      )}
    </div>
  );
}
