import { useState } from "react";
import { deleteBusiness } from "./api.js";

export function BusinessList({ businesses, onRefresh, onOpenInvites }) {
  const [busy, setBusy] = useState(null);

  const onDelete = async (b) => {
    if (!confirm(
      `Delete "${b.name}" and ALL its data? This is permanent.\n\n` +
      `${b.customer_count} customers, ${b.job_count} jobs, ${b.conversation_count} conversations will be gone.`
    )) return;
    setBusy(`del-${b.id}`);
    try {
      await deleteBusiness(b.id);
      await onRefresh();
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    } finally {
      setBusy(null);
    }
  };

  if (businesses.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-subtle)" }}>
        <p style={{ fontSize: 14 }}>No businesses yet. Click "+ New Business" to onboard the first one.</p>
      </div>
    );
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th style={{ width: 50 }}>ID</th>
          <th>Name</th>
          <th>Twilio number</th>
          <th>Owner</th>
          <th className="right">Customers</th>
          <th className="right">Jobs</th>
          <th className="right">Convos</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {businesses.map((b) => (
          <tr key={b.id}>
            <td className="mono muted">#{b.id}</td>
            <td style={{ fontWeight: 500 }}>{b.name}</td>
            <td className="mono">{b.twilio_number}</td>
            <td>
              {b.owner_auth0_id ? (
                <span className="status completed" style={{ fontSize: 11 }}>
                  <span className="dot" /> Linked
                </span>
              ) : (
                <span className="status pending" style={{ fontSize: 11 }}>
                  <span className="dot" /> Unlinked
                </span>
              )}
            </td>
            <td className="right num">{b.customer_count}</td>
            <td className="right num">{b.job_count}</td>
            <td className="right num">{b.conversation_count}</td>
            <td className="right">
              <button
                className="btn ghost"
                style={{ marginRight: 6 }}
                onClick={() => onOpenInvites(b)}
                title="Manage invites"
              >
                Invites
              </button>
              <button
                className="btn ghost"
                onClick={() => onDelete(b)}
                disabled={busy === `del-${b.id}`}
                title="Delete business"
                style={{ color: "var(--error, #e53e3e)" }}
              >
                {busy === `del-${b.id}` ? "Deleting…" : "Delete"}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
