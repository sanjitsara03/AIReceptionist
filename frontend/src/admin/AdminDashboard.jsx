import { useEffect, useState } from "react";
import { listBusinesses, clearSecret } from "./api.js";
import { BusinessList } from "./BusinessList.jsx";
import { NewBusinessModal } from "./NewBusinessModal.jsx";
import { InviteModal } from "./InviteModal.jsx";

export function AdminDashboard() {
  const [businesses, setBusinesses] = useState(null);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [invitesFor, setInvitesFor] = useState(null);

  const refresh = async () => {
    setError(null);
    try {
      const list = await listBusinesses();
      setBusinesses(list);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => { refresh(); }, []);

  const signOut = () => {
    clearSecret();
    window.location.reload();
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <header style={{
        padding: "14px 28px", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <div style={{ fontSize: 13, color: "var(--text-subtle)" }}>AI Receptionist</div>
          <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em" }}>
            Platform admin
          </div>
        </div>
        <button className="btn ghost" onClick={signOut}>Sign out</button>
      </header>

      <main style={{ padding: 28, maxWidth: 1200, margin: "0 auto" }}>
        <div className="row-flex" style={{ justifyContent: "space-between", marginBottom: 18 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>Businesses</h1>
            <p className="muted" style={{ fontSize: 13 }}>
              {businesses === null
                ? "Loading…"
                : `${businesses.length} ${businesses.length === 1 ? "business" : "businesses"} on the platform`}
            </p>
          </div>
          <button className="btn primary" onClick={() => setCreating(true)}>
            + New Business
          </button>
        </div>

        {error && (
          <div style={{
            padding: 14, marginBottom: 14, borderRadius: 4,
            background: "oklch(0.92 0.04 25)", color: "var(--text)", fontSize: 13,
          }}>
            Failed to load: {error}
          </div>
        )}

        {businesses !== null && (
          <div style={{
            background: "var(--bg-elev)", border: "1px solid var(--border)",
            borderRadius: "var(--r-md)", overflow: "hidden",
          }}>
            <BusinessList
              businesses={businesses}
              onRefresh={refresh}
              onOpenInvites={(b) => setInvitesFor(b)}
            />
          </div>
        )}
      </main>

      {creating && (
        <NewBusinessModal
          onClose={() => setCreating(false)}
          onCreated={refresh}
        />
      )}

      {invitesFor && (
        <InviteModal
          business={invitesFor}
          onClose={() => setInvitesFor(null)}
        />
      )}
    </div>
  );
}
