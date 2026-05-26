import { useEffect, useState } from 'react';
import { I } from '../icons.jsx';
import { useData } from '../DataContext.jsx';
import {
  patchBusiness,
  createTechnician,
  patchTechnician,
  deleteTechnician,
  fetchAllSlots,
  createSlot,
  createSlotsBulk,
  deleteSlot,
} from '../api.js';

export function SettingsView() {
  const { data, getToken, reload } = useData();
  const { business = {}, technicians } = data;
  const [section, setSection] = useState("business");

  const sections = [
    { k: "business",     label: "Business info" },
    { k: "ai",           label: "AI receptionist" },
    { k: "technicians",  label: "Technicians" },
    { k: "availability", label: "Availability" },
    { k: "phone",        label: "Phone & SMS" },
  ];

  return (
    <>
      <div className="content-header">
        <div className="content-title-block">
          <h1>Settings</h1>
          <p>Configure how the AI receptionist behaves for {business.name ?? "your business"}.</p>
        </div>
      </div>

      <div className="settings-grid">
        <nav className="settings-section-list">
          {sections.map((s) => (
            <button
              key={s.k}
              className={"settings-section-item " + (section === s.k ? "active" : "")}
              onClick={() => setSection(s.k)}
            >
              {s.label}
            </button>
          ))}
        </nav>

        <div>
          {section === "business"     && <BusinessForm business={business} getToken={getToken} reload={reload} />}
          {section === "ai"           && <AIForm       business={business} getToken={getToken} reload={reload} />}
          {section === "technicians"  && <Technicians  technicians={technicians} getToken={getToken} reload={reload} />}
          {section === "availability" && <Availability technicians={technicians} getToken={getToken} reload={reload} />}
          {section === "phone"        && <PhoneInfo    business={business} />}
        </div>
      </div>
    </>
  );
}

// ---------- Business info ----------

function BusinessForm({ business, getToken, reload }) {
  const [form, setForm] = useState({
    name: business.name ?? "",
    address: business.address ?? "",
    services: business.services ?? "",
    hours: business.hours ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);

  useEffect(() => {
    setForm({
      name: business.name ?? "",
      address: business.address ?? "",
      services: business.services ?? "",
      hours: business.hours ?? "",
    });
  }, [business.id, business.name, business.address, business.services, business.hours]);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const save = async () => {
    setSaving(true);
    try {
      const token = await getToken();
      await patchBusiness(token, form);
      await reload();
      setSavedAt(new Date());
    } catch (err) {
      alert("Save failed: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="settings-card">
      <h3>Business info</h3>
      <p className="desc">Used by the AI when callers ask "where are you" or "what hours are you open".</p>

      <Field label="Business name" hint="Shown to customers in confirmations.">
        <input value={form.name} onChange={onChange("name")} />
      </Field>
      <Field label="Address">
        <input value={form.address} onChange={onChange("address")} />
      </Field>
      <Field label="Hours" hint="Free-form text — the AI quotes this verbatim.">
        <input value={form.hours} onChange={onChange("hours")} />
      </Field>
      <Field label="Services offered" hint="The AI will only book services on this list.">
        <textarea value={form.services} onChange={onChange("services")} />
      </Field>

      <SaveBar saving={saving} savedAt={savedAt} onSave={save} />
    </div>
  );
}

// ---------- AI receptionist ----------

function AIForm({ business, getToken, reload }) {
  const [form, setForm] = useState({
    voice_greeting: business.voice_greeting ?? "",
    system_prompt: business.system_prompt ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);

  useEffect(() => {
    setForm({
      voice_greeting: business.voice_greeting ?? "",
      system_prompt: business.system_prompt ?? "",
    });
  }, [business.id, business.voice_greeting, business.system_prompt]);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const save = async () => {
    setSaving(true);
    try {
      const token = await getToken();
      await patchBusiness(token, form);
      await reload();
      setSavedAt(new Date());
    } catch (err) {
      alert("Save failed: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="settings-card">
      <h3>AI personality</h3>
      <p className="desc">Tune how the AI introduces itself and how it speaks. Changes apply to the next call or SMS.</p>

      <Field label="Voice greeting" hint="First line on every inbound call.">
        <input value={form.voice_greeting} onChange={onChange("voice_greeting")}
               placeholder="Hi! You've reached Joe's Plumbing. How can I help you today?" />
      </Field>

      <Field label="System prompt" hint="Advanced — edit the instructions sent to Claude on every turn.">
        <textarea
          style={{ minHeight: 220 }}
          value={form.system_prompt}
          onChange={onChange("system_prompt")}
          placeholder="You are an AI receptionist for…"
        />
      </Field>

      <SaveBar saving={saving} savedAt={savedAt} onSave={save} />
    </div>
  );
}

// ---------- Technicians ----------

function Technicians({ technicians, getToken, reload }) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ name: "", phone: "", active: true });
  const [busy, setBusy] = useState(null);

  const onAdd = async () => {
    if (!draft.name || !draft.phone) return;
    setBusy("add");
    try {
      const token = await getToken();
      await createTechnician(token, draft);
      await reload();
      setDraft({ name: "", phone: "", active: true });
      setAdding(false);
    } catch (err) {
      alert("Add failed: " + err.message);
    } finally {
      setBusy(null);
    }
  };

  const onToggleActive = async (tech) => {
    setBusy(`active-${tech.id}`);
    try {
      const token = await getToken();
      await patchTechnician(token, tech.id, { active: !tech.active });
      await reload();
    } finally {
      setBusy(null);
    }
  };

  const onDelete = async (tech) => {
    if (!confirm(`Remove ${tech.name}?`)) return;
    setBusy(`del-${tech.id}`);
    try {
      const token = await getToken();
      await deleteTechnician(token, tech.id);
      await reload();
    } catch (err) {
      alert("Delete failed: " + err.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="settings-card">
      <h3>Technicians</h3>
      <p className="desc">Field staff the AI assigns to bookings.</p>

      <table className="table" style={{ marginTop: 8 }}>
        <thead>
          <tr>
            <th>Name</th>
            <th>Phone</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {technicians.map((t) => (
            <tr key={t.id} style={{ cursor: "default" }}>
              <td>{t.name}</td>
              <td className="mono">{t.phone}</td>
              <td>
                <button
                  className={"status " + (t.active ? "completed" : "cancelled")}
                  onClick={() => onToggleActive(t)}
                  disabled={busy === `active-${t.id}`}
                  style={{ cursor: "pointer", border: "none" }}
                >
                  <span className="dot" /> {t.active ? "Active" : "Inactive"}
                </button>
              </td>
              <td className="right">
                <button
                  className="btn ghost"
                  onClick={() => onDelete(t)}
                  disabled={busy === `del-${t.id}`}
                  title="Remove"
                >
                  <I.X />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {adding ? (
        <div style={{ marginTop: 14, display: "flex", gap: 8, alignItems: "center" }}>
          <input
            placeholder="Name"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <input
            placeholder="+15551234567"
            value={draft.phone}
            onChange={(e) => setDraft({ ...draft, phone: e.target.value })}
          />
          <button className="btn primary" onClick={onAdd} disabled={busy === "add"}>
            {busy === "add" ? "Adding…" : "Add"}
          </button>
          <button className="btn ghost" onClick={() => setAdding(false)}>Cancel</button>
        </div>
      ) : (
        <button className="btn" style={{ marginTop: 14 }} onClick={() => setAdding(true)}>
          <I.Plus /> Add technician
        </button>
      )}
    </div>
  );
}

// ---------- Availability ----------

function Availability({ technicians, getToken, reload }) {
  const [slots, setSlots] = useState(null);
  const [busy, setBusy] = useState(null);
  const [mode, setMode] = useState(null); // null | 'one' | 'bulk'

  const loadSlots = async () => {
    const token = await getToken();
    const list = await fetchAllSlots(token);
    setSlots(list);
  };

  useEffect(() => { loadSlots(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onDelete = async (slot) => {
    if (!slot.is_available) {
      alert("This slot is booked. Cancel the job first.");
      return;
    }
    if (!confirm(`Delete this slot for ${slot.technician_name}?`)) return;
    setBusy(`del-${slot.id}`);
    try {
      const token = await getToken();
      await deleteSlot(token, slot.id);
      await loadSlots();
      await reload();
    } catch (err) {
      alert("Delete failed: " + err.message);
    } finally {
      setBusy(null);
    }
  };

  // Group slots by day for display
  const byDay = {};
  (slots || []).forEach((s) => {
    const d = new Date(s.start_time).toDateString();
    (byDay[d] = byDay[d] || []).push(s);
  });

  if (technicians.length === 0) {
    return (
      <div className="settings-card">
        <h3>Availability</h3>
        <p className="desc">Add a technician first before scheduling availability.</p>
      </div>
    );
  }

  return (
    <div className="settings-card">
      <h3>Availability</h3>
      <p className="desc">
        Time slots the AI receptionist can book customers into. Slots highlighted in red are already booked.
      </p>

      <div className="row-flex" style={{ marginBottom: 14, gap: 8 }}>
        <button className="btn" onClick={() => setMode("one")}>
          <I.Plus /> Add one slot
        </button>
        <button className="btn primary" onClick={() => setMode("bulk")}>
          <I.Plus /> Bulk add (recurring)
        </button>
        <button className="btn ghost" onClick={loadSlots}>
          <I.Refresh /> Refresh
        </button>
      </div>

      {mode === "one" && (
        <AddOneSlotForm
          technicians={technicians}
          onClose={() => setMode(null)}
          onSaved={async () => {
            setMode(null);
            await loadSlots();
            await reload();
          }}
          getToken={getToken}
        />
      )}

      {mode === "bulk" && (
        <BulkSlotForm
          technicians={technicians}
          onClose={() => setMode(null)}
          onSaved={async () => {
            setMode(null);
            await loadSlots();
            await reload();
          }}
          getToken={getToken}
        />
      )}

      <div style={{ marginTop: 4 }}>
        {slots == null ? (
          <div className="muted" style={{ fontSize: 13 }}>Loading slots…</div>
        ) : Object.keys(byDay).length === 0 ? (
          <div className="muted" style={{ fontSize: 13, padding: "16px 0" }}>
            No slots scheduled yet. Use "Bulk add" to set up a week of availability.
          </div>
        ) : (
          Object.entries(byDay).map(([day, daySlots]) => (
            <div key={day} style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 6, color: "var(--text-subtle)" }}>
                {day}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {daySlots.map((s) => (
                  <div
                    key={s.id}
                    style={{
                      padding: "6px 10px",
                      borderRadius: 4,
                      border: "1px solid var(--border)",
                      background: s.is_available ? "var(--bg-elev)" : "oklch(0.92 0.04 25)",
                      fontSize: 12,
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                    }}
                  >
                    <span className="mono">{fmtTime(s.start_time)}–{fmtTime(s.end_time)}</span>
                    <span className="muted" style={{ fontSize: 11 }}>{s.technician_name}</span>
                    {s.is_available ? (
                      <button
                        onClick={() => onDelete(s)}
                        disabled={busy === `del-${s.id}`}
                        style={{
                          background: "none",
                          border: "none",
                          color: "var(--text-subtle)",
                          cursor: "pointer",
                          padding: 0,
                          display: "flex",
                          alignItems: "center",
                        }}
                        title="Delete slot"
                      >
                        <I.X />
                      </button>
                    ) : (
                      <span className="muted" style={{ fontSize: 10, fontWeight: 500 }}>booked</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function AddOneSlotForm({ technicians, onClose, onSaved, getToken }) {
  const [form, setForm] = useState({
    technician_id: technicians[0]?.id ?? "",
    date: todayISO(),
    start_time: "09:00",
    end_time: "10:00",
  });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const token = await getToken();
      await createSlot(token, {
        technician_id: Number(form.technician_id),
        start_time: localToISO(form.date, form.start_time),
        end_time: localToISO(form.date, form.end_time),
      });
      await onSaved();
    } catch (err) {
      alert("Add failed: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: 14, background: "var(--surface)", borderRadius: "var(--r-md)", border: "1px solid var(--border)", marginBottom: 14 }}>
      <div className="row-flex" style={{ gap: 8, flexWrap: "wrap" }}>
        <select value={form.technician_id} onChange={(e) => setForm({ ...form, technician_id: e.target.value })}>
          {technicians.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        <input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
        <span className="muted">to</span>
        <input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
        <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Adding…" : "Add"}</button>
        <button className="btn ghost" onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}

function BulkSlotForm({ technicians, onClose, onSaved, getToken }) {
  const [form, setForm] = useState({
    technician_id: technicians[0]?.id ?? "",
    start_date: todayISO(),
    end_date: addDaysISO(14),
    weekdays: [0, 1, 2, 3, 4], // Mon-Fri
    day_start_hour: 9,
    day_end_hour: 17,
    slot_minutes: 120,
  });
  const [saving, setSaving] = useState(false);

  const toggleDay = (d) => {
    setForm({
      ...form,
      weekdays: form.weekdays.includes(d)
        ? form.weekdays.filter((x) => x !== d)
        : [...form.weekdays, d].sort(),
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const token = await getToken();
      const created = await createSlotsBulk(token, {
        technician_id: Number(form.technician_id),
        start_date: localToISO(form.start_date, "00:00"),
        end_date: localToISO(form.end_date, "00:00"),
        weekdays: form.weekdays,
        day_start_hour: Number(form.day_start_hour),
        day_end_hour: Number(form.day_end_hour),
        slot_minutes: Number(form.slot_minutes),
      });
      alert(`Created ${created.length} slots.`);
      await onSaved();
    } catch (err) {
      alert("Bulk add failed: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const dayLabels = ["M", "T", "W", "T", "F", "S", "S"];

  return (
    <div style={{ padding: 14, background: "var(--surface)", borderRadius: "var(--r-md)", border: "1px solid var(--border)", marginBottom: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "10px 14px", alignItems: "center" }}>
        <label className="muted" style={{ fontSize: 12.5 }}>Technician</label>
        <select value={form.technician_id} onChange={(e) => setForm({ ...form, technician_id: e.target.value })}>
          {technicians.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>

        <label className="muted" style={{ fontSize: 12.5 }}>Date range</label>
        <div className="row-flex" style={{ gap: 6 }}>
          <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
          <span className="muted">to</span>
          <input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
        </div>

        <label className="muted" style={{ fontSize: 12.5 }}>Weekdays</label>
        <div className="row-flex" style={{ gap: 4 }}>
          {dayLabels.map((d, i) => (
            <button
              key={i}
              onClick={() => toggleDay(i)}
              style={{
                width: 30, height: 30, borderRadius: 4,
                border: "1px solid " + (form.weekdays.includes(i) ? "var(--accent)" : "var(--border)"),
                background: form.weekdays.includes(i) ? "var(--accent-soft)" : "var(--bg-elev)",
                color: "var(--text)",
                fontSize: 12, fontWeight: 600, cursor: "pointer",
              }}
            >{d}</button>
          ))}
        </div>

        <label className="muted" style={{ fontSize: 12.5 }}>Hours</label>
        <div className="row-flex" style={{ gap: 6 }}>
          <input type="number" min="0" max="23" value={form.day_start_hour} onChange={(e) => setForm({ ...form, day_start_hour: e.target.value })} style={{ width: 70 }} />
          <span className="muted">to</span>
          <input type="number" min="1" max="24" value={form.day_end_hour} onChange={(e) => setForm({ ...form, day_end_hour: e.target.value })} style={{ width: 70 }} />
        </div>

        <label className="muted" style={{ fontSize: 12.5 }}>Slot length</label>
        <div className="row-flex" style={{ gap: 6 }}>
          <input type="number" min="15" max="480" step="15" value={form.slot_minutes} onChange={(e) => setForm({ ...form, slot_minutes: e.target.value })} style={{ width: 80 }} />
          <span className="muted">minutes</span>
        </div>
      </div>

      <div className="row-flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
        <button className="btn ghost" onClick={onClose} disabled={saving}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={saving}>{saving ? "Creating…" : "Create slots"}</button>
      </div>
    </div>
  );
}

// ---------- Phone & SMS (read-only) ----------

function PhoneInfo({ business }) {
  return (
    <div className="settings-card">
      <h3>Phone & SMS</h3>
      <p className="desc">Twilio number the AI receptionist answers on.</p>
      <Field label="Active number" hint="Forward your business line to this number. Provisioned via Twilio.">
        <div className="row-flex">
          <input
            value={business.twilio_number ?? ""}
            readOnly
            style={{ maxWidth: 220, fontFamily: "var(--font-mono)" }}
          />
          <span className="status completed"><span className="dot" /> Verified</span>
        </div>
      </Field>
    </div>
  );
}

// ---------- Shared bits ----------

function Field({ label, hint, children }) {
  return (
    <div className="field">
      <div className="field-label">
        <div className="name">{label}</div>
        {hint && <div className="hint">{hint}</div>}
      </div>
      <div className="field-control">{children}</div>
    </div>
  );
}

function SaveBar({ saving, savedAt, onSave }) {
  return (
    <div className="row-flex" style={{ justifyContent: "flex-end", marginTop: 14, gap: 12, alignItems: "center" }}>
      {savedAt && (
        <span className="muted" style={{ fontSize: 12 }}>
          Saved {savedAt.toLocaleTimeString("en-US", { timeZone: "America/Los_Angeles" })}
        </span>
      )}
      <button className="btn primary" onClick={onSave} disabled={saving}>
        <I.Check /> {saving ? "Saving…" : "Save changes"}
      </button>
    </div>
  );
}

// ---------- date / time helpers ----------
// All operator inputs (date pickers, time pickers) are interpreted as
// California time, and all rendered times are shown in California time,
// regardless of what timezone the operator's browser is in.

const TZ = "America/Los_Angeles";

function ptYMD(date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(date);
  const get = (t) => parts.find((p) => p.type === t)?.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function todayISO() {
  return ptYMD(new Date());
}

function addDaysISO(days) {
  // Add `days` to "today in PT". Build a UTC noon anchor for stability
  // around DST transitions, then re-format in PT.
  const today = todayISO();
  const [y, m, d] = today.split("-").map(Number);
  const anchor = new Date(Date.UTC(y, m - 1, d, 12, 0, 0));
  anchor.setUTCDate(anchor.getUTCDate() + days);
  return ptYMD(anchor);
}

function localToISO(date, time) {
  // date "YYYY-MM-DD" and time "HH:MM" are operator inputs interpreted in
  // California time. Convert to a UTC ISO string for the backend.
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  // Strategy: build a candidate UTC instant assuming +00:00, then measure
  // what wall-clock time it lands at in PT, and shift by the delta. Works
  // through DST.
  const guess = new Date(Date.UTC(y, m - 1, d, hh, mm));
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ, hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(guess);
  const get = (t) => Number(parts.find((p) => p.type === t)?.value);
  const asPT = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
  const offsetMs = guess.getTime() - asPT;
  return new Date(guess.getTime() + offsetMs).toISOString();
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ });
}
