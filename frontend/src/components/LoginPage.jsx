import { useEffect, useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';

const BASE = "/api";

export function LoginPage() {
  const { loginWithRedirect, isLoading } = useAuth0();
  const [invite, setInvite] = useState(null);
  const [inviteError, setInviteError] = useState(null);

  const inviteToken = new URLSearchParams(window.location.search).get("invite");

  useEffect(() => {
    if (!inviteToken) return;
    fetch(`${BASE}/invites/${inviteToken}`)
      .then((r) => {
        if (!r.ok) throw new Error(r.status === 410 ? "This invite has expired or already been used." : "Invalid invite link.");
        return r.json();
      })
      .then(setInvite)
      .catch((e) => setInviteError(e.message));
  }, [inviteToken]);

  const handleLogin = () => {
    const appState = inviteToken ? { inviteToken, returnTo: "/" } : { returnTo: "/" };
    loginWithRedirect({ appState });
  };

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      height: "100vh",
      background: "var(--bg)",
      gap: 24,
    }}>
      <div style={{ textAlign: "center", maxWidth: 360 }}>
        <div style={{
          width: 48, height: 48, borderRadius: 12,
          background: "var(--accent)",
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 20px", fontSize: 22,
        }}>
          📞
        </div>

        {inviteError ? (
          <>
            <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Invalid invite</h1>
            <p style={{ fontSize: 13, color: "var(--text-subtle)", lineHeight: 1.6 }}>{inviteError}</p>
          </>
        ) : inviteToken && !invite ? (
          <p style={{ fontSize: 13, color: "var(--text-subtle)" }}>Checking invite…</p>
        ) : invite ? (
          <>
            <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>
              You're invited to join {invite.business_name}
            </h1>
            <p style={{ fontSize: 13, color: "var(--text-subtle)", marginBottom: 28, lineHeight: 1.6 }}>
              Sign in or create an account to access your dashboard.
            </p>
            <button
              className="btn primary"
              style={{ width: "100%", justifyContent: "center", padding: "10px 0", fontSize: 14 }}
              onClick={handleLogin}
              disabled={isLoading}
            >
              {isLoading ? "Loading…" : `Accept & sign in`}
            </button>
          </>
        ) : (
          <>
            <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>AI Receptionist</h1>
            <p style={{ fontSize: 14, color: "var(--text-subtle)", marginBottom: 28, lineHeight: 1.6 }}>
              Sign in to manage your bookings, customers, and AI receptionist settings.
            </p>
            <button
              className="btn primary"
              style={{ width: "100%", justifyContent: "center", padding: "10px 0", fontSize: 14 }}
              onClick={handleLogin}
              disabled={isLoading}
            >
              {isLoading ? "Loading…" : "Sign in"}
            </button>
          </>
        )}
      </div>
      <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
        Powered by Auth0 · Secured with RS256 JWT
      </p>
    </div>
  );
}
