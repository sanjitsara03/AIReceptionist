import { Fragment } from 'react';
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

export function TopBar({ crumbs, title, liveCall }) {
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
        <LiveCallPill call={liveCall} />
        <div className="search">
          <I.Search />
          <input placeholder="Search jobs, customers, conversations…" />
          <kbd>⌘K</kbd>
        </div>
        <button className="icon-btn" title="Notifications"><I.Bell /></button>
        <button className="btn">
          <I.Plus /> New job
        </button>
      </div>
    </header>
  );
}

function LiveCallPill({ call }) {
  if (!call) {
    return (
      <div className="live-pill" title="AI is idle">
        <span className="live-dot idle" />
        <span>AI idle</span>
      </div>
    );
  }
  return (
    <div className="live-pill" title="AI is on a call">
      <span className="live-dot" />
      <span>AI on call</span>
      <span className="who">· {call.who} · {call.duration}</span>
    </div>
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

