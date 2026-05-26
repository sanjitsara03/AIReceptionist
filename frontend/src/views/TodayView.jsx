import { Fragment } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { I } from '../icons.jsx';
import { Avatar, Card } from '../components/Shell.jsx';
import { useData } from '../DataContext.jsx';

function fmtMoney(n) {
  return "$" + (n ?? 0).toLocaleString("en-US");
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function todayLabel() {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
    timeZone: "America/Los_Angeles",
  });
}

export function TodayView({ onOpenConversation, onOpenJob }) {
  const { user } = useAuth0();
  const { data } = useData();
  const { jobs, kpis, feed, technicians, customers } = data;
  const today = jobs.filter((j) => j.date === "Today");
  const firstName = (user?.name || user?.nickname || user?.email || "").split(/[ @]/)[0];

  return (
    <>
      <div className="content-header">
        <div className="content-title-block">
          <h1>{greeting()}{firstName ? `, ${firstName}` : ""}</h1>
          <p>{todayLabel()} · {today.length} {today.length === 1 ? "job" : "jobs"} on the books today.</p>
        </div>
        <div className="row-flex">
          <button className="btn ghost" onClick={() => window.location.reload()}><I.Refresh /> Refresh</button>
        </div>
      </div>

      <div className="kpi-grid">
        <div className="kpi hero">
          <div className="kpi-label"><I.Bot /> AI booked today</div>
          <div className="kpi-value">
            {fmtMoney(kpis.ai_booked_revenue)}<span className="unit"> est.</span>
          </div>
          <div className="kpi-delta">
            <span className="up mono">↑ {kpis.ai_booked_today ?? 0} jobs</span>
            <span>across {kpis.calls_handled ?? 0} {kpis.calls_handled === 1 ? "conversation" : "conversations"} today.</span>
          </div>
        </div>

        <div className="kpi">
          <div className="kpi-label"><I.Phone /> Conversations today</div>
          <div className="kpi-value tnum">{kpis.calls_handled ?? 0}</div>
          <div className="kpi-delta"><span className="mono muted">SMS + voice combined</span></div>
        </div>

        <div className="kpi">
          <div className="kpi-label"><I.Users /> Total customers</div>
          <div className="kpi-value tnum">{kpis.customers_total ?? 0}</div>
          <div className="kpi-delta"><span className="mono muted">all-time</span></div>
        </div>
      </div>

      <div className="row-2">
        <Card
          title="Today's schedule"
          icon="Calendar"
          action={
            <div className="row-flex" style={{ gap: 8 }}>
              <span className="muted" style={{ fontSize: 11.5 }}>
                {technicians.length} technicians ·
              </span>
              <a className="card-link" href="#" onClick={(e) => e.preventDefault()}>
                Open full calendar <I.ArrowRight />
              </a>
            </div>
          }
          padded={false}
        >
          <Schedule jobs={today} technicians={technicians} customers={customers} onOpenJob={onOpenJob} />
        </Card>

        <Card
          title="Recent calls"
          icon="Sparkle"
          action={
            <a className="card-link" href="#" onClick={(e) => e.preventDefault()}>
              View all <I.ArrowRight />
            </a>
          }
          padded={false}
        >
          <div>
            {feed.map((f) => {
              const ico =
                f.kind === "booked" ? "Check" :
                f.kind === "cancelled" ? "X" :
                f.kind === "reschedule" ? "Refresh" :
                "Phone";
              const IconC = I[ico];
              return (
                <div key={f.id} className="feed-item" onClick={() => onOpenConversation && onOpenConversation()}>
                  <div className={"feed-ico " + f.kind}><IconC /></div>
                  <div className="feed-body">
                    <div className="feed-title">
                      <span className="who">{f.who} </span>
                      <span className="verb">{f.verb}</span>
                    </div>
                    <div className="feed-meta">{f.meta}</div>
                  </div>
                  <div className="feed-time">{f.when}</div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <Card title="Technician utilization" icon="Users">
        <TechUtilization technicians={technicians} jobs={today} />
      </Card>
    </>
  );
}

function Schedule({ jobs, technicians, customers, onOpenJob }) {
  const hours = [];
  for (let h = 7; h <= 17; h++) hours.push(h);
  const fmt = (h) => {
    const ampm = h >= 12 ? "PM" : "AM";
    const hh = h % 12 === 0 ? 12 : h % 12;
    return `${hh} ${ampm}`;
  };
  const toMin = (t) => {
    const [hh, mm] = t.split(":").map(Number);
    return hh * 60 + mm;
  };
  const top = (t) => ((toMin(t) - 7 * 60) / 60) * 42;
  const height = (start, end) => ((toMin(end) - toMin(start)) / 60) * 42 - 4;

  return (
    <div>
      <div className="schedule" style={{ gridTemplateColumns: "60px repeat(" + technicians.length + ", 1fr)" }}>
        <div style={{ borderRight: "1px solid var(--divider)", borderBottom: "1px solid var(--border)", background: "var(--surface)", height: 32 }} />
        {technicians.map((t) => (
          <div key={t.id} className="schedule-tech-header">
            <span className="dot" />
            <Avatar name={t.name} size={18} />
            <span>{t.name}</span>
          </div>
        ))}
      </div>

      <div className="schedule" style={{ gridTemplateColumns: "60px repeat(" + technicians.length + ", 1fr)", position: "relative" }}>
        {hours.map((h) => (
          <Fragment key={h}>
            <div className="schedule-hour">{fmt(h)}</div>
            {technicians.map((t) => (
              <div key={t.id + "-" + h} className="schedule-cell" />
            ))}
          </Fragment>
        ))}

        {jobs.map((j) => {
          const techIdx = technicians.findIndex((t) => t.id === j.tech_id);
          if (techIdx === -1) return null;
          const left = `calc(60px + ${techIdx} * ((100% - 60px) / ${technicians.length}))`;
          const width = `calc((100% - 60px) / ${technicians.length})`;
          const cust = customers.find((c) => c.id === j.customer_id);
          return (
            <div
              key={j.id}
              className={"schedule-block " + j.status}
              style={{
                position: "absolute",
                top: top(j.start),
                height: height(j.start, j.end),
                left,
                width,
                padding: "5px 8px",
                margin: "0 4px",
                boxSizing: "border-box",
                cursor: "pointer",
              }}
              onClick={() => onOpenJob && onOpenJob(j.id)}
            >
              <div className="blk-customer">{cust?.name}</div>
              <div className="blk-type">{j.type}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TechUtilization({ technicians, jobs }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {technicians.map((t) => {
        const tjobs = jobs.filter((j) => j.tech_id === t.id);
        const hours = tjobs.reduce((sum, j) => {
          const [sh, sm] = j.start.split(":").map(Number);
          const [eh, em] = j.end.split(":").map(Number);
          return sum + (eh + em / 60 - sh - sm / 60);
        }, 0);
        const pct = Math.min(100, (hours / 8) * 100);
        return (
          <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Avatar name={t.name} size={26} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 12.5, fontWeight: 500 }}>{t.name}</span>
                <span className="mono muted" style={{ fontSize: 11.5 }}>
                  {hours.toFixed(1)} / 8h · {tjobs.length} jobs
                </span>
              </div>
              <div style={{ height: 6, background: "var(--surface-2)", borderRadius: 3, overflow: "hidden" }}>
                <div
                  style={{
                    width: pct + "%",
                    height: "100%",
                    background: pct > 90 ? "var(--warn)" : "var(--accent)",
                    transition: "width 0.3s",
                  }}
                />
              </div>
            </div>
            <span className="mono" style={{ fontSize: 12, color: "var(--text)", minWidth: 32, textAlign: "right" }}>
              {Math.round(pct)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}

