import { useState } from "react";
import { createBusiness, createInvite } from "./api.js";

const E164_RE = /^\+\d{10,15}$/;

export function NewBusinessModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "",
    twilio_number: "",
    address: "",
    services: "",
    hours: "",
    voice_greeting: "",
    system_prompt: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null); // { business, invite_url }

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!form.name.trim()) return setError("Name is required.");
    if (!E164_RE.test(form.twilio_number.trim())) {
      return setError("Twilio number must be in E.164 format, e.g. +15551234567");
    }

    setSaving(true);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, v.trim() || null]).filter(([_, v]) => v !== "")
      );
      payload.name = form.name.trim();
      payload.twilio_number = form.twilio_number.trim();

      const business = await createBusiness(payload);
      const invite = await createInvite(business.id, 7);
      const inviteUrl = `${window.location.origin}/?invite=${invite.token}`;

      setSuccess({ business, invite_url: inviteUrl });
      onCreated();
    } catch (err) {
      setError(err.message || "Failed to create business");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div style={{
        position: "fixed", top: "50%", left: "50%",
        transform: "translate(-50%, -50%)",
        width: 560, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto",
        background: "var(--bg-elev)", border: "1px solid var(--border)",
        borderRadius: "var(--r-md)", padding: 22, zIndex: 100,
        boxShadow: "0 8px 32px oklch(0 0 0 / 0.25)",
      }}>
        {success ? (
          <SuccessScreen
            business={success.business}
            inviteUrl={success.invite_url}
            onClose={onClose}
          />
        ) : (
          <form onSubmit={submit}>
            <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>New business</h2>
            <p className="muted" style={{ fontSize: 12.5, marginBottom: 16 }}>
              Create a business record. A 7-day invite URL will be generated automatically for the new owner.
            </p>

            <Field label="Name" required>
              <input value={form.name} onChange={onChange("name")} placeholder="Mike's HVAC" />
            </Field>

            <Field label="Twilio number" required hint="Must be unique. E.164 format (e.g. +15551234567).">
              <input value={form.twilio_number} onChange={onChange("twilio_number")} placeholder="+15551234567" />
            </Field>

            <Field label="Address">
              <input value={form.address} onChange={onChange("address")} placeholder="123 Main St, City, State" />
            </Field>

            <Field label="Hours">
              <input value={form.hours} onChange={onChange("hours")} placeholder="Mon-Fri 9am-5pm" />
            </Field>

            <Field label="Services">
              <textarea value={form.services} onChange={onChange("services")}
                        placeholder="HVAC repair, AC installation, …" />
            </Field>

            <Field label="Voice greeting" hint="First line on every inbound call.">
              <input value={form.voice_greeting} onChange={onChange("voice_greeting")}
                     placeholder="Hi! You've reached Mike's HVAC. How can I help?" />
            </Field>

            <Field label="System prompt" hint="Optional — overrides the default AI prompt.">
              <textarea value={form.system_prompt} onChange={onChange("system_prompt")}
                        style={{ minHeight: 100 }} />
            </Field>

            {error && (
              <div style={{ color: "var(--error, #e53e3e)", fontSize: 12.5, marginTop: 10 }}>
                {error}
              </div>
            )}

            <div className="row-flex" style={{ justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
              <button type="button" className="btn ghost" onClick={onClose} disabled={saving}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={saving}>
                {saving ? "Creating…" : "Create + generate invite"}
              </button>
            </div>
          </form>
        )}
      </div>
    </>
  );
}

function SuccessScreen({ business, inviteUrl, onClose }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // older browsers: fall back to manual select
    }
  };

  return (
    <div>
      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>
        Created "{business.name}" (id #{business.id})
      </h2>
      <p className="muted" style={{ fontSize: 12.5, marginBottom: 16 }}>
        Send this invite URL to the new business owner. It's valid for 7 days and can only be used once.
      </p>

      <div style={{
        padding: 12, background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12,
        wordBreak: "break-all", marginBottom: 12,
      }}>
        {inviteUrl}
      </div>

      <div className="row-flex" style={{ justifyContent: "flex-end", gap: 8 }}>
        <button className="btn" onClick={copy}>
          {copied ? "✓ Copied" : "Copy link"}
        </button>
        <button className="btn primary" onClick={onClose}>Done</button>
      </div>
    </div>
  );
}

function Field({ label, required, hint, children }) {
  return (
    <div className="field" style={{ flexDirection: "column", alignItems: "stretch", gap: 4 }}>
      <div className="field-label">
        <div className="name" style={{ fontSize: 12.5, fontWeight: 500 }}>
          {label} {required && <span style={{ color: "var(--error, #e53e3e)" }}>*</span>}
        </div>
        {hint && <div className="hint" style={{ fontSize: 11.5, color: "var(--text-subtle)" }}>{hint}</div>}
      </div>
      <div className="field-control">{children}</div>
    </div>
  );
}
