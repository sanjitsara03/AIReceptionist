import { useEffect, useState } from "react";
import { storedSecret, listBusinesses } from "./api.js";
import { AdminLogin } from "./AdminLogin.jsx";
import { AdminDashboard } from "./AdminDashboard.jsx";

export function AdminApp() {
  const [authed, setAuthed] = useState(null); // null = unknown, true = ok, false = needs login

  useEffect(() => {
    // If there's a stored secret, try it. If it works → authed. Otherwise → login.
    if (!storedSecret()) {
      setAuthed(false);
      return;
    }
    listBusinesses()
      .then(() => setAuthed(true))
      .catch(() => setAuthed(false));
  }, []);

  if (authed === null) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
                    height: "100vh", background: "var(--bg)" }}>
        <span style={{ color: "var(--text-subtle)", fontSize: 13 }}>Loading…</span>
      </div>
    );
  }

  if (!authed) {
    return <AdminLogin onAuthed={() => setAuthed(true)} />;
  }

  return <AdminDashboard />;
}
