import { useEffect, useMemo, useState } from 'react';
import { I } from '../icons.jsx';
import { StatusBadge, Avatar, Card, Source } from '../components/Shell.jsx';
import { useData } from '../DataContext.jsx';
import {
  updateJobStatus,
  createJob,
  rescheduleJob,
  fetchAvailableSlots,
} from '../api.js';

// ---------------------------------------------------------------------------
// Jobs list view
// ---------------------------------------------------------------------------

export function JobsView({ onOpenJob, creating: creatingProp = false, onCloseCreate }) {
  const { data } = useData();
  const { jobs, customers, technicians } = data;
  const [filter, setFilter] = useState("all");
  const [creatingLocal, setCreatingLocal] = useState(false);
  const creating = creatingProp || creatingLocal;
  const closeCreate = () => { setCreatingLocal(false); onCloseCreate?.(); };

  const counts = useMemo(() => {
    const c = { all: jobs.length, confirmed: 0, pending: 0, completed: 0, cancelled: 0, no_show: 0, in_progress: 0 };
    jobs.forEach((j) => { c[j.status] = (c[j.status] || 0) + 1; });
    return c;
  }, [jobs]);

  const filtered = filter === "all" ? jobs : jobs.filter((j) => j.status === filter);
  const byCust = (id) => customers.find((c) => c.id === id);
  const byTech = (id) => technicians.find((t) => t.id === id);

  const chips = [
    { k: "all",         label: "All" },
    { k: "confirmed",   label: "Confirmed" },
    { k: "in_progress", label: "In progress" },
    { k: "pending",     label: "Pending" },
    { k: "completed",   label: "Completed" },
    { k: "cancelled",   label: "Cancelled" },
    { k: "no_show",     label: "No-show" },
  ];

  return (
    <>
      <div className="content-header">
        <div className="content-title-block">
          <h1>Jobs</h1>
          <p>{jobs.length} appointments — {jobs.filter((j) => j.source === "ai").length} booked by the AI.</p>
        </div>
        <div className="row-flex">
          <button className="btn primary" onClick={() => setCreatingLocal(true)}>
            <I.Plus /> New job
          </button>
        </div>
      </div>

      <div className="filter-bar">
        {chips.map((c) => (
          <button key={c.k} className={"chip " + (filter === c.k ? "active" : "")} onClick={() => setFilter(c.k)}>
            <span>{c.label}</span>
            <span className="count">{counts[c.k] || 0}</span>
          </button>
        ))}
      </div>

      <Card padded={false}>
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 70 }}>Job</th>
              <th>Customer</th>
              <th>Service</th>
              <th>Technician</th>
              <th>When</th>
              <th>Status</th>
              <th>Source</th>
              <th className="right">Est.</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((j) => {
              const cust = byCust(j.customer_id);
              const tech = byTech(j.tech_id);
              return (
                <tr key={j.id} onClick={() => onOpenJob(j.id)}>
                  <td className="mono">#{j.id}</td>
                  <td>
                    <div className="cell-with-avatar">
                      <Avatar name={cust?.name || "?"} />
                      <div className="cell-stack">
                        <span>{cust?.name}</span>
                        <span className="sub">{cust?.phone}</span>
                      </div>
                    </div>
                  </td>
                  <td>{j.type}</td>
                  <td>
                    <div className="cell-with-avatar">
                      <Avatar name={tech?.name || "?"} size={20} />
                      <span>{tech?.name}</span>
                    </div>
                  </td>
                  <td>
                    <div className="cell-stack">
                      <span>{j.date}</span>
                      <span className="sub">{j.start} – {j.end}</span>
                    </div>
                  </td>
                  <td><StatusBadge value={j.status} /></td>
                  <td><Source src={j.source} /></td>
                  <td className="right num">{j.est != null ? `$${j.est}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      {creating && <NewJobModal customers={customers} onClose={closeCreate} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Job detail drawer — with wired action buttons
// ---------------------------------------------------------------------------

export function JobDrawer({ jobId, onClose }) {
  const { data, getToken, reload } = useData();
  const { jobs, customers, technicians, conversations } = data;

  const [busy, setBusy] = useState(null);
  const [rescheduling, setRescheduling] = useState(false);

  if (!jobId) return null;
  const job = jobs.find((j) => j.id === jobId);
  if (!job) return null;
  const cust = customers.find((c) => c.id === job.customer_id);
  const tech = technicians.find((t) => t.id === job.tech_id);
  const conv = conversations.find((c) => c.customer_id === job.customer_id);

  const callStatus = async (status, label) => {
    setBusy(label);
    try {
      const token = await getToken();
      await updateJobStatus(token, job.id, status);
      await reload();
    } catch (err) {
      alert(`Failed to ${label.toLowerCase()}: ${err.message}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-header">
          <button className="icon-btn" onClick={onClose}><I.X /></button>
          <div>
            <div className="h-title">{job.type}</div>
            <div className="h-sub">#{job.id} · {job.date} · {job.start}–{job.end}</div>
          </div>
          <div style={{ marginLeft: "auto" }} className="row-flex">
            <StatusBadge value={job.status} />
          </div>
        </div>

        <div className="drawer-body">
          <div className="detail-panel">
            <div className="detail-row">
              <div className="label">Customer</div>
              <div className="value">
                <div className="cell-with-avatar">
                  <Avatar name={cust?.name || "?"} size={32} />
                  <div>
                    <div style={{ fontWeight: 600 }}>{cust?.name}</div>
                    <div className="mono muted" style={{ fontSize: 12 }}>{cust?.phone}</div>
                  </div>
                </div>
              </div>
            </div>
            <div className="detail-row">
              <div className="label">Technician</div>
              <div className="value">
                <div className="cell-with-avatar">
                  <Avatar name={tech?.name || "?"} size={24} />
                  <span>{tech?.name}</span>
                  {tech?.phone && (
                    <span className="muted mono" style={{ fontSize: 11.5, marginLeft: 6 }}>{tech.phone}</span>
                  )}
                </div>
              </div>
            </div>
            <div className="detail-row">
              <div className="label">Service</div>
              <div className="value">{job.type}</div>
            </div>
            <div className="detail-row">
              <div className="label">Estimate</div>
              <div className="value num">{job.est != null ? `$${job.est}.00` : "—"}</div>
            </div>
            <div className="detail-row">
              <div className="label">Booked by</div>
              <div className="value">
                <Source src={job.source} />
                {job.source === "ai" && conv && (
                  <span className="muted" style={{ marginLeft: 6, fontSize: 12 }}>
                    via {conv.channel === "voice" ? "phone call" : "SMS"} at {conv.started_at}
                  </span>
                )}
              </div>
            </div>
            <div className="detail-row">
              <div className="label">Reminder</div>
              <div className="value">
                {job.reminder_sent ? (
                  <span className="status completed"><span className="dot" /> Sent 24h before</span>
                ) : (
                  <span className="muted" style={{ fontSize: 12 }}>Not sent yet</span>
                )}
              </div>
            </div>
          </div>

          {conv && (
            <Card title="Booking conversation" icon="Chat" padded={false}>
              <div style={{ padding: "12px 18px", maxHeight: 260, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                {(conv.messages || []).slice(-6).map((m, i) => (
                  <div key={i} className={"bubble " + (m.dir === "out" ? "out" : "in")} style={{ fontSize: 12.5, padding: "6px 11px", maxWidth: "85%" }}>
                    {m.body}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {rescheduling ? (
            <ReschedulePanel
              job={job}
              onClose={() => setRescheduling(false)}
              onDone={async () => {
                setRescheduling(false);
                await reload();
              }}
            />
          ) : (
            <div className="row-flex" style={{ justifyContent: "flex-end", gap: 8 }}>
              {job.status !== "cancelled" && (
                <button className="btn ghost" disabled={!!busy} onClick={() => callStatus("cancelled", "Cancel")}>
                  {busy === "Cancel" ? "Cancelling…" : "Cancel job"}
                </button>
              )}
              <button className="btn" disabled={!!busy} onClick={() => setRescheduling(true)}>
                Reschedule
              </button>
              {job.status !== "completed" && (
                <button className="btn primary" disabled={!!busy} onClick={() => callStatus("completed", "Mark complete")}>
                  <I.Check /> {busy === "Mark complete" ? "Saving…" : "Mark complete"}
                </button>
              )}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------
// Reschedule panel — inline slot picker
// ---------------------------------------------------------------------------

function ReschedulePanel({ job, onClose, onDone }) {
  const { getToken } = useData();
  const [slots, setSlots] = useState(null);
  const [picked, setPicked] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      const list = await fetchAvailableSlots(token);
      setSlots(list);
    })();
  }, [getToken]);

  const save = async () => {
    if (!picked) return;
    setSaving(true);
    try {
      const token = await getToken();
      await rescheduleJob(token, job.id, picked);
      await onDone();
    } catch (err) {
      alert("Reschedule failed: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Pick a new time" icon="Calendar" padded={true}>
      {slots == null ? (
        <div className="muted" style={{ fontSize: 13 }}>Loading available slots…</div>
      ) : slots.length === 0 ? (
        <div className="muted" style={{ fontSize: 13 }}>No available slots in the next 14 days.</div>
      ) : (
        <select
          value={picked ?? ""}
          onChange={(e) => setPicked(Number(e.target.value))}
          style={{ width: "100%", marginBottom: 12 }}
        >
          <option value="" disabled>Select a slot</option>
          {slots.map((s) => (
            <option key={s.id} value={s.id}>
              {fmtSlot(s)} — {s.technician_name}
            </option>
          ))}
        </select>
      )}
      <div className="row-flex" style={{ justifyContent: "flex-end", gap: 8 }}>
        <button className="btn ghost" onClick={onClose} disabled={saving}>Back</button>
        <button className="btn primary" onClick={save} disabled={!picked || saving}>
          {saving ? "Saving…" : "Confirm reschedule"}
        </button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// New job modal
// ---------------------------------------------------------------------------

function NewJobModal({ customers, onClose }) {
  const { getToken, reload } = useData();
  const [slots, setSlots] = useState(null);
  const [form, setForm] = useState({
    customer_id: customers[0]?.id ?? "",
    time_slot_id: "",
    job_type: "",
    estimate: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      const list = await fetchAvailableSlots(token);
      setSlots(list);
    })();
  }, [getToken]);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const save = async () => {
    if (!form.customer_id || !form.time_slot_id || !form.job_type) {
      alert("Customer, time slot, and service are required.");
      return;
    }
    setSaving(true);
    try {
      const token = await getToken();
      await createJob(token, {
        customer_id: Number(form.customer_id),
        time_slot_id: Number(form.time_slot_id),
        job_type: form.job_type,
        estimate: form.estimate ? Number(form.estimate) : null,
        notes: form.notes || null,
      });
      await reload();
      onClose();
    } catch (err) {
      alert("Create failed: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div
        style={{
          position: "fixed",
          top: "50%", left: "50%",
          transform: "translate(-50%, -50%)",
          width: 480, maxWidth: "92vw",
          background: "var(--bg-elev)",
          border: "1px solid var(--border)",
          borderRadius: "var(--r-md)",
          padding: 22,
          zIndex: 100,
          boxShadow: "0 8px 32px oklch(0 0 0 / 0.25)",
        }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>New job</h2>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 16 }}>
          Manually book an appointment. Source will be marked "Manual".
        </p>

        <div className="field" style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}>
          <div className="name" style={{ fontSize: 12.5, fontWeight: 500 }}>Customer</div>
          <select value={form.customer_id} onChange={onChange("customer_id")}>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>{c.name} — {c.phone}</option>
            ))}
          </select>
        </div>

        <div className="field" style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}>
          <div className="name" style={{ fontSize: 12.5, fontWeight: 500 }}>Time slot</div>
          {slots == null ? (
            <div className="muted" style={{ fontSize: 12 }}>Loading slots…</div>
          ) : slots.length === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>No available slots — add availability first.</div>
          ) : (
            <select value={form.time_slot_id} onChange={onChange("time_slot_id")}>
              <option value="" disabled>Select a slot</option>
              {slots.map((s) => (
                <option key={s.id} value={s.id}>
                  {fmtSlot(s)} — {s.technician_name}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="field" style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}>
          <div className="name" style={{ fontSize: 12.5, fontWeight: 500 }}>Service</div>
          <input
            placeholder="e.g. Drain cleaning"
            value={form.job_type}
            onChange={onChange("job_type")}
          />
        </div>

        <div className="field" style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}>
          <div className="name" style={{ fontSize: 12.5, fontWeight: 500 }}>Estimate ($, optional)</div>
          <input
            type="number"
            placeholder="180"
            value={form.estimate}
            onChange={onChange("estimate")}
          />
        </div>

        <div className="field" style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}>
          <div className="name" style={{ fontSize: 12.5, fontWeight: 500 }}>Notes (optional)</div>
          <textarea value={form.notes} onChange={onChange("notes")} />
        </div>

        <div className="row-flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
          <button className="btn ghost" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="btn primary" onClick={save} disabled={saving || !slots?.length}>
            {saving ? "Creating…" : "Create job"}
          </button>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function fmtSlot(s) {
  const d = new Date(s.start_time);
  return d.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Los_Angeles",
  });
}
