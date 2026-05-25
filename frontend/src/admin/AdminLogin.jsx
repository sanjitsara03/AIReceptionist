import { useState } from "react";
import { storeSecret, listBusinesses, storedSecret } from "./api.js";

export function AdminLogin({ onAuthed }) {
  const [secret, setSecret] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Store, then test it by hitting a real endpoint.
      storeSecret(secret);
      await listBusinesses();
      onAuthed();
    } catch (err) {
      if (err.status === 403) {
        setError("Invalid admin secret.");
      } else {
        setError(`Couldn't reach the backend: ${err.message}`);
      }
      setBusy(false);
    }
  };

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      height: "100vh", background: "var(--bg)", gap: 24,
    }}>
      <div style={{ textAlign: "center", maxWidth: 380 }}>
        <div style={{
          width: 48, height: 48, borderRadius: 12,
          background: "var(--accent)", display: "flex", alignItems: "center",
          justifyContent: "center", margin: "0 auto 20px", fontSize: 22,
        }}>
          🔑
        </div>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Platform admin</h1>
        <p style={{ fontSize: 14, color: "var(--text-subtle)", marginBottom: 28, lineHeight: 1.6 }}>
          For onboarding new businesses to the AI Receptionist platform.
        </p>

        <form onSubmit={submit}>
          <input
            type="password"
            placeholder="Admin secret"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            autoFocus
            style={{
              width: "100%", padding: "10px 12px", fontSize: 14,
              fontFamily: "var(--font-mono)", marginBottom: 12,
            }}
          />
          <button
            type="submit"
            className="btn primary"
            disabled={busy || !secret}
            style={{ width: "100%", justifyContent: "center", padding: "10px 0", fontSize: 14 }}
          >
            {busy ? "Verifying…" : "Sign in"}
          </button>
        </form>

        {error && (
          <div style={{
            marginTop: 16, fontSize: 12.5, color: "var(--error, #e53e3e)",
            textAlign: "center",
          }}>
            {error}
          </div>
        )}

        {storedSecret() && !error && (
          <p style={{ fontSize: 11.5, color: "var(--text-faint)", marginTop: 14 }}>
            A previous secret is stored locally — entering a new value will replace it.
          </p>
        )}
      </div>
    </div>
  );
}
