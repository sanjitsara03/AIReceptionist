import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import {
  BASE,
  fetchAuthMe,
  claimBusiness,
  fetchTechnicians,
  fetchJobs,
  fetchCustomers,
  fetchConversations,
  fetchDashboardSummary,
  fetchDashboardFeed,
} from "./api.js";

const AUDIENCE = import.meta.env.VITE_AUTH0_AUDIENCE;

// Empty shape used as the initial state. We deliberately do NOT seed with
// AIRDATA — that way, if any field is blank in the UI, it means the backend
// didn't return it. Easier to debug "missing data" vs "fake data showing".
const EMPTY_DATA = {
  business: null,
  technicians: [],
  jobs: [],
  customers: [],
  conversations: [],
  kpis: {},
  feed: [],
};

const DataContext = createContext(null);

export function DataProvider({ children }) {
  const { getAccessTokenSilently, isAuthenticated } = useAuth0();
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [usingLive, setUsingLive] = useState(false);
  const [noBusiness, setNoBusiness] = useState(false);
  const [loadError, setLoadError] = useState(null);

  const getToken = useCallback(() => {
    return getAccessTokenSilently({ authorizationParams: { audience: AUDIENCE } });
  }, [getAccessTokenSilently]);

  const load = useCallback(async () => {
    try {
      const token = await getToken();

      let business = await fetchAuthMe(token);
      if (!business) {
        const inviteToken = sessionStorage.getItem("pendingInviteToken");
        if (inviteToken) {
          sessionStorage.removeItem("pendingInviteToken");
          business = await claimBusiness(token, inviteToken);
        } else {
          setNoBusiness(true);
          setLoading(false);
          return;
        }
      }

      const [technicians, jobs, customers, conversations, summary, feed] =
        await Promise.all([
          fetchTechnicians(token),
          fetchJobs(token),
          fetchCustomers(token),
          fetchConversations(token),
          fetchDashboardSummary(token),
          fetchDashboardFeed(token),
        ]);

      const normalizedJobs = normalizeJobs(jobs);
      setData({
        business: normalizeBusiness(business),
        technicians: normalizeTechnicians(technicians),
        jobs: normalizedJobs,
        customers: normalizeCustomers(customers, normalizedJobs),
        conversations: normalizeConversations(conversations),
        kpis: normalizeKpis(summary),
        feed: normalizeFeed(feed),
      });
      setUsingLive(true);
      setLoadError(null);
      setNoBusiness(false);
    } catch (err) {
      console.error("Failed to load live data:", err);
      setLoadError(err.message || "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    load();
  }, [isAuthenticated, load]);

  // Open an SSE stream that triggers a reload whenever the backend says something changed.
  // Debounce so a burst of events (e.g., a booking → conversation + job) becomes one reload.
  useEffect(() => {
    if (!isAuthenticated) return;
    let es;
    let debounceId;
    let cancelled = false;

    (async () => {
      try {
        const token = await getToken();
        if (cancelled) return;
        es = new EventSource(`${BASE}/events/stream?token=${encodeURIComponent(token)}`);

        const triggerReload = () => {
          clearTimeout(debounceId);
          debounceId = setTimeout(() => load(), 300);
        };

        es.addEventListener("conversation.updated", triggerReload);
        es.addEventListener("job.created", triggerReload);
        es.addEventListener("job.updated", triggerReload);

        es.onerror = () => {
          // EventSource auto-reconnects; nothing to do here.
        };
      } catch (err) {
        console.warn("SSE setup failed:", err);
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(debounceId);
      if (es) es.close();
    };
  }, [isAuthenticated, getToken, load]);

  return (
    <DataContext.Provider
      value={{ data, loading, usingLive, noBusiness, loadError, getToken, reload: load }}
    >
      {children}
    </DataContext.Provider>
  );
}

export function useData() {
  return useContext(DataContext);
}

// --- normalizers ---

function normalizeBusiness(b) {
  return {
    id: b.id,
    name: b.name,
    twilio_number: b.twilio_number,
    services: b.services,
    hours: b.hours,
    address: b.address,
  };
}

function normalizeTechnicians(list) {
  return list.map((t) => ({
    id: t.id,
    name: t.name,
    phone: t.phone,
    active: t.active,
    initials: initials(t.name),
    color: techColor(t.id),
  }));
}

function normalizeJobs(list) {
  return list.map((j) => ({
    id: j.id,
    customer_id: j.customer?.id,
    tech_id: j.technician?.id ?? null,
    type: j.job_type,
    status: j.status,
    source: j.source,
    est: j.estimate ?? null,
    // TodayView's Schedule does "HH:MM".split(":").map(Number) so we need 24h
    start: j.start_time ? fmt24(j.start_time) : null,
    end: j.end_time ? fmt24(j.end_time) : null,
    date: j.start_time ? relativeDate(j.start_time) : null,
    notes: j.notes,
    reminder_sent: j.reminder_sent,
    created_at: j.created_at,
  }));
}

function normalizeCustomers(list, allJobs = []) {
  // Pre-bucket jobs by customer for O(n+m) lifetime calc instead of O(n*m).
  const byCustomer = new Map();
  for (const j of allJobs) {
    if (!j.customer_id) continue;
    (byCustomer.get(j.customer_id) ?? byCustomer.set(j.customer_id, []).get(j.customer_id)).push(j);
  }
  return list.map((c) => {
    const theirs = byCustomer.get(c.id) ?? [];
    const lifetime = theirs
      .filter((j) => j.status === "completed")
      .reduce((sum, j) => sum + (j.est ?? 0), 0);
    return {
      id: c.id,
      name: c.name,
      phone: c.phone,
      created: fmtDate(c.created_at),
      jobs: c.job_count,
      lifetime,
    };
  });
}

function normalizeConversations(list) {
  return list.map((c) => ({
    id: c.id,
    customer_id: c.customer?.id,
    customer_name: c.customer?.name ?? "Unknown",
    channel: c.channel,
    started_at: fmtRelativeDateTime(c.created_at),
    last_at: fmtTime(c.updated_at),
    unread: false,
    booked:
      c.messages?.some(
        (m) => m.direction === "outbound" && m.body.toLowerCase().includes("booked")
      ) ?? false,
    preview: c.messages?.length
      ? c.messages[c.messages.length - 1].body.slice(0, 80)
      : "",
    messages: (c.messages ?? []).map((m) => ({
      dir: m.direction === "inbound" ? "in" : "out",
      body: m.body,
      time: fmtTime(m.created_at),
    })),
  }));
}

function normalizeKpis(s) {
  return {
    ai_booked_today: s.ai_booked_today,
    ai_booked_revenue: s.ai_booked_revenue,
    human_booked_today: s.human_booked_today,
    calls_handled: s.conversations_today,
    avg_response_sec: 4.2,
    customers_total: s.total_customers,
    confirmed: s.confirmed,
    in_progress: s.in_progress,
    pending: s.pending,
    completed: s.completed,
    no_shows: s.no_shows,
    cancelled: s.cancelled,
  };
}

function normalizeFeed(list) {
  return list.map((f, i) => ({
    id: i + 1,
    kind: f.kind,
    who: f.customer_name,
    verb: f.verb,
    when: fmtRelativeTime(f.when_iso),
    meta: `via ${f.channel}${f.estimate ? ` · $${f.estimate}` : ""}`,
    time: fmtTime(f.when_iso),
  }));
}

// --- helpers ---

function initials(name) {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

const TECH_COLORS = [250, 155, 75, 320, 35];
function techColor(id) {
  return TECH_COLORS[(id - 1) % TECH_COLORS.length];
}

// All times are rendered in California time regardless of the viewer's
// browser locale — this is a US-West home-service business.
const TZ = "America/Los_Angeles";

function fmtTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ });
}

function fmt24(iso) {
  // 24-hour "HH:MM" in PT — used by TodayView's schedule math.
  // Use hourCycle "h23" so midnight is "00" instead of "24" (some
  // Chromium versions emit "24" with just hour12:false).
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ, hourCycle: "h23", hour: "2-digit", minute: "2-digit",
  }).formatToParts(new Date(iso));
  let h = parts.find((p) => p.type === "hour")?.value ?? "00";
  if (h === "24") h = "00";
  const m = parts.find((p) => p.type === "minute")?.value ?? "00";
  return `${h}:${m}`;
}

function fmtDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: TZ });
}

// Returns {y, m, d} for a Date as observed in California, so relative-day
// math doesn't shift when the viewer is in a different timezone.
function ptYMD(date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(date);
  const get = (t) => Number(parts.find((p) => p.type === t)?.value);
  return { y: get("year"), m: get("month"), d: get("day") };
}

function relativeDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  const a = ptYMD(d);
  const b = ptYMD(new Date());
  const dayA = Date.UTC(a.y, a.m - 1, a.d);
  const dayB = Date.UTC(b.y, b.m - 1, b.d);
  const diff = (dayA - dayB) / 86400000;
  if (diff === 0) return "Today";
  if (diff === -1) return "Yesterday";
  if (diff === 1) return "Tomorrow";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: TZ });
}

function fmtRelativeDateTime(iso) {
  if (!iso) return "";
  return `${relativeDate(iso)} · ${fmtTime(iso)}`;
}

function fmtRelativeTime(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso)) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  const a = ptYMD(new Date(iso));
  const b = ptYMD(new Date());
  if (a.y === b.y && a.m === b.m && a.d === b.d - 1) return "Yest";
  return fmtDate(iso);
}
