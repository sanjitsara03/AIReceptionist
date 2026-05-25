import { useEffect, useState } from "react";
import { listInvites, createInvite } from "./api.js";

export function InviteModal({ business, onClose }) {
  const [invites, setInvites] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copiedToken, setCopiedToken] = useState(null);

  const refresh = async () => {
    try {
      const list = await listInvites(business.id);
      setInvites(list);
    } catch (err) {
      alert(`Failed to load invites: ${err.message}`);
    }
  };

  useEffect(() => { refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const generate = async () => {
    setBusy(true);
    try {
      await createInvite(business.id, 7);
      await refresh();
    } catch (err) {
      alert(`Generate failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const copyUrl = async (token) => {
    const url = `${window.location.origin}/?invite=${token}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopiedToken(token);
      setTimeout(() => setCopiedToken(null), 1500);
    } catch {}
  };

  const isExpired = (iso) => new Date(iso) < new Date();

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div style={{
        position: "fixed", top: "50%", left: "50%",
        transform: "translate(-50%, -50%)",
        width: 640, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto",
        background: "var(--bg-elev)", border: "1px solid var(--border)",
        borderRadius: "var(--r-md)", padding: 22, zIndex: 100,
        boxShadow: "0 8px 32px oklch(0 0 0 / 0.25)",
      }}>
        <div className="row-flex" style={{ justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 2 }}>
              Invites for {business.name}
            </h2>
            <p className="muted" style={{ fontSize: 12 }}>#{business.id} · {business.twilio_number}</p>
          </div>
          <button className="btn primary" onClick={generate} disabled={busy}>
            {busy ? "Generating…" : "+ New invite (7d)"}
          </button>
        </div>

        {invites === null ? (
          <div className="muted" style={{ fontSize: 13 }}>Loading…</div>
        ) : invites.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: "var(--text-subtle)", fontSize: 13 }}>
            No invites generated yet for this business.
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Token</th>
                <th>Status</th>
                <th>Expires</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {invites.map((inv) => {
                const expired = isExpired(inv.expires_at);
                const usable = !inv.claimed && !expired;
                return (
                  <tr key={inv.token}>
                    <td className="mono" style={{ fontSize: 11.5, maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {inv.token}
                    </td>
                    <td>
                      {inv.claimed ? (
                        <span className="status completed" style={{ fontSize: 11 }}>
                          <span className="dot" /> Claimed
                        </span>
                      ) : expired ? (
                        <span className="status cancelled" style={{ fontSize: 11 }}>
                          <span className="dot" /> Expired
                        </span>
                      ) : (
                        <span className="status pending" style={{ fontSize: 11 }}>
                          <span className="dot" /> Active
                        </span>
                      )}
                    </td>
                    <td className="mono muted" style={{ fontSize: 11.5 }}>
                      {new Date(inv.expires_at).toLocaleString()}
                    </td>
                    <td className="right">
                      {usable && (
                        <button className="btn ghost" onClick={() => copyUrl(inv.token)}>
                          {copiedToken === inv.token ? "✓ Copied" : "Copy URL"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        <div className="row-flex" style={{ justifyContent: "flex-end", marginTop: 16 }}>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </>
  );
}
