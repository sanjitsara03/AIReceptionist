import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { I } from '../icons.jsx';

const NAV_BASE = [
  { key: "today",         label: "Today",         icon: "Home"     },
  { key: "jobs",          label: "Jobs",          icon: "Briefcase"},
  { key: "conversations", label: "Conversations", icon: "Chat"    },
  { key: "customers",     label: "Customers",     icon: "Users"   },
  { key: "settings",      label: "Settings",      icon: "Settings"},
];

function brandMark(name = "") {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase() || "??";
}

function fmtPhone(raw) {
  if (!raw) return "";
  const d = raw.replace(/\D/g, "");
  if (d.length === 11 && d.startsWith("1")) {
    return `+1 (${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7)}`;
  }
  return raw;
}

export function Sidebar({ active, onSelect, business, counts }) {
  const { user, logout } = useAuth0();
  const name = business?.name ?? "—";
  const phone = fmtPhone(business?.twilio_number);

  const nav = NAV_BASE.map((n) => ({
    ...n,
    badge:
      n.key === "jobs"          ? counts?.jobs ?? null :
      n.key === "conversations" ? counts?.conversations ?? null :
      n.key === "customers"     ? counts?.customers ?? null :
      null,
  }));

  const displayName = user?.name || user?.nickname || user?.email || "Signed in";
  const userInitials = (user?.name || user?.email || "?")
    .split(/[ @]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();

  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <div className="sb-brand-mark">{brandMark(name)}</div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="sb-brand-name">{name}</div>
          {phone && <div className="sb-brand-sub mono">{phone}</div>}
        </div>
      </div>

      <div className="sb-section">Operations</div>
      <nav className="sb-nav">
        {nav.map((item) => {
          const IconCmp = I[item.icon];
          return (
            <button
              key={item.key}
              className={"sb-item" + (active === item.key ? " active" : "")}
              onClick={() => onSelect(item.key)}
            >
              <IconCmp className="ico" />
              <span>{item.label}</span>
              {item.badge != null && <span className="badge mono">{item.badge}</span>}
            </button>
          );
        })}
      </nav>

      <div className="sb-footer">
        <div className="sb-avatar">{userInitials}</div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="sb-user-name">{displayName}</div>
          <div className="sb-user-role">{user?.email}</div>
        </div>
        <button
          className="icon-btn"
          title="Sign out"
          onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
        >
          <I.MoreH />
        </button>
      </div>
    </aside>
  );
}

export function TopBar({
  crumbs,
  title,
  data,
  onNewJob,
  onOpenJob,
  onOpenCustomer,
  onOpenConversation,
}) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const wrapRef = useRef(null);

  // Close the dropdown when clicking outside the search wrapper.
  useEffect(() => {
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setFocused(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // ⌘K / Ctrl+K focuses the search input.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        wrapRef.current?.querySelector("input")?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !data) return null;
    const customers = (data.customers ?? [])
      .filter((c) => c.name?.toLowerCase().includes(q) || c.phone?.includes(q))
      .slice(0, 5);
    const jobs = (data.jobs ?? [])
      .filter((j) => String(j.id) === q || j.type?.toLowerCase().includes(q))
      .slice(0, 5);
    const conversations = (data.conversations ?? [])
      .filter((c) => c.preview?.toLowerCase().includes(q))
      .slice(0, 5);
    return { customers, jobs, conversations };
  }, [query, data]);

  const pick = (fn) => {
    fn();
    setQuery("");
    setFocused(false);
  };

  const empty =
    results &&
    results.customers.length === 0 &&
    results.jobs.length === 0 &&
    results.conversations.length === 0;

  const custName = (id) => data?.customers?.find((c) => c.id === id)?.name ?? "—";

  return (
    <header className="topbar">
      <div>
        <div className="topbar-title">{title}</div>
        {crumbs && (
          <div className="topbar-crumbs">
            {crumbs.map((c, i) => (
              <Fragment key={i}>
                {i > 0 && <span className="sep">/</span>}
                <span>{c}</span>
              </Fragment>
            ))}
          </div>
        )}
      </div>

      <div className="topbar-actions">
        <div className="search" ref={wrapRef} style={{ position: "relative" }}>
          <I.Search />
          <input
            placeholder="Search jobs, customers, conversations…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setFocused(true); }}
            onFocus={() => setFocused(true)}
          />
          <kbd>⌘K</kbd>

          {focused && results && (
            <div
              style={{
                position: "absolute", top: "calc(100% + 6px)", left: 0, right: 0,
                background: "var(--bg-elev)", border: "1px solid var(--border)",
                borderRadius: "var(--r-md)", boxShadow: "0 8px 28px oklch(0 0 0 / 0.18)",
                maxHeight: 420, overflowY: "auto", zIndex: 50, padding: 4,
              }}
            >
              {empty && (
                <div style={{ padding: "14px 12px", fontSize: 12.5, color: "var(--text-subtle)" }}>
                  No matches for "{query}".
                </div>
              )}
              {results.customers.length > 0 && (
                <SearchGroup label="Customers">
                  {results.customers.map((c) => (
                    <SearchItem key={"c" + c.id} onClick={() => pick(() => onOpenCustomer?.(c.id))}>
                      <I.User />
                      <span>{c.name}</span>
                      <span className="mono muted" style={{ marginLeft: "auto", fontSize: 11.5 }}>{c.phone}</span>
                    </SearchItem>
                  ))}
                </SearchGroup>
              )}
              {results.jobs.length > 0 && (
                <SearchGroup label="Jobs">
                  {results.jobs.map((j) => (
                    <SearchItem key={"j" + j.id} onClick={() => pick(() => onOpenJob?.(j.id))}>
                      <I.Briefcase />
                      <span className="mono" style={{ color: "var(--text-subtle)" }}>#{j.id}</span>
                      <span>{j.type}</span>
                      <span className="muted" style={{ marginLeft: "auto", fontSize: 11.5 }}>
                        {custName(j.customer_id)} · {j.date}
                      </span>
                    </SearchItem>
                  ))}
                </SearchGroup>
              )}
              {results.conversations.length > 0 && (
                <SearchGroup label="Conversations">
                  {results.conversations.map((c) => (
                    <SearchItem key={"v" + c.id} onClick={() => pick(() => onOpenConversation?.(c.id))}>
                      <I.Chat />
                      <span>{custName(c.customer_id)}</span>
                      <span className="muted" style={{ marginLeft: 8, fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                        {c.preview}
                      </span>
                    </SearchItem>
                  ))}
                </SearchGroup>
              )}
            </div>
          )}
        </div>
        <button className="btn" onClick={() => onNewJob?.()}>
          <I.Plus /> New job
        </button>
      </div>
    </header>
  );
}

function SearchGroup({ label, children }) {
  return (
    <div style={{ padding: "6px 0" }}>
      <div style={{
        fontSize: 10, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase",
        color: "var(--text-subtle)", padding: "4px 10px 6px",
      }}>{label}</div>
      {children}
    </div>
  );
}

function SearchItem({ children, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 8, width: "100%",
        padding: "8px 10px", border: 0, background: "transparent",
        cursor: "pointer", borderRadius: 6, fontSize: 13, color: "var(--text)",
        textAlign: "left",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover, oklch(0.96 0.005 250))")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      {children}
    </button>
  );
}

export function StatusBadge({ value }) {
  const labels = {
    confirmed:   "Confirmed",
    completed:   "Completed",
    pending:     "Pending",
    in_progress: "In progress",
    cancelled:   "Cancelled",
    no_show:     "No-show",
  };
  return (
    <span className={"status " + value}>
      <span className="dot" />
      {labels[value] || value}
    </span>
  );
}

export function Channel({ kind, withLabel = true }) {
  const Ico = kind === "voice" ? I.Phone : I.Sms;
  return (
    <span className="channel">
      <Ico />
      {withLabel && <span>{kind === "voice" ? "Voice" : "SMS"}</span>}
    </span>
  );
}

export function Avatar({ name, size = 24 }) {
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
  return (
    <span className="avatar-sm" style={{ width: size, height: size, fontSize: size * 0.43 }}>
      {initials}
    </span>
  );
}

export function Card({ title, icon, action, children, padded = true }) {
  const Ico = icon ? I[icon] : null;
  return (
    <section className="card">
      {(title || action) && (
        <div className="card-header">
          <div className="card-title">
            {Ico && <Ico />}
            {title}
          </div>
          {action}
        </div>
      )}
      {padded ? <div className="card-body">{children}</div> : children}
    </section>
  );
}

export function Source({ src }) {
  if (src === "ai") {
    return (
      <span className="channel" title="Booked by AI receptionist">
        <I.Bot />
        <span>AI</span>
      </span>
    );
  }
  return (
    <span className="channel" title="Manual entry">
      <I.User />
      <span>Manual</span>
    </span>
  );
}

