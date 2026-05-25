import { useState } from 'react';
import { I } from '../icons.jsx';
import { StatusBadge, Channel, Avatar, Card } from '../components/Shell.jsx';
import { useData } from '../DataContext.jsx';

export function CustomersView() {
  const { data } = useData();
  const { customers, jobs, conversations } = data;
  const [selected, setSelected] = useState(customers[0]?.id ?? null);
  const [query, setQuery] = useState("");

  if (customers.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-subtle)" }}>
        <h1 style={{ fontSize: 18, marginBottom: 8 }}>No customers yet</h1>
        <p style={{ fontSize: 13 }}>Customers will appear here after their first SMS or call.</p>
      </div>
    );
  }

  const filtered = customers.filter((c) =>
    !query || c.name.toLowerCase().includes(query.toLowerCase()) || c.phone.includes(query)
  );
  const cust = customers.find((c) => c.id === selected) || customers[0];
  const custJobs = jobs.filter((j) => j.customer_id === cust.id);
  const custConvs = conversations.filter((c) => c.customer_id === cust.id);

  return (
    <>
      <div className="content-header">
        <div className="content-title-block">
          <h1>Customers</h1>
          <p>{customers.length} {customers.length === 1 ? "customer" : "customers"} in your address book.</p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "var(--density-gap)", alignItems: "flex-start" }}>
        <Card padded={false}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--divider)", display: "flex", gap: 10 }}>
            <div className="search" style={{ flex: 1 }}>
              <I.Search />
              <input
                placeholder="Search by name or phone"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={{ width: "100%" }}
              />
            </div>
            <button className="chip"><I.Filter /> Filters</button>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Phone</th>
                <th className="right">Jobs</th>
                <th className="right">Lifetime</th>
                <th>Added</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => setSelected(c.id)}
                  className={selected === c.id ? "selected" : ""}
                >
                  <td>
                    <div className="cell-with-avatar">
                      <Avatar name={c.name} />
                      <span>{c.name}</span>
                    </div>
                  </td>
                  <td className="mono">{c.phone}</td>
                  <td className="right num">{c.jobs}</td>
                  <td className="right num">${c.lifetime}</td>
                  <td className="muted">{c.created}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <div style={{ position: "sticky", top: 0, display: "flex", flexDirection: "column", gap: "var(--density-gap)" }}>
          <div className="detail-panel">
            <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 4 }}>
              <Avatar name={cust.name} size={48} />
              <div>
                <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em" }}>{cust.name}</div>
                <div className="mono muted" style={{ fontSize: 12.5, marginTop: 2 }}>{cust.phone}</div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 0, borderTop: "1px solid var(--divider)", paddingTop: 14, marginTop: 6 }}>
              <Stat label="Jobs" value={custJobs.length} />
              <Stat label="Lifetime" value={"$" + cust.lifetime.toLocaleString()} />
              <Stat label="Since" value={cust.created} mono={false} />
            </div>
          </div>

          <Card title="Job history" icon="Briefcase" padded={false}>
            {custJobs.length === 0 ? (
              <div className="empty" style={{ padding: 14 }}>No jobs yet.</div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Date</th>
                    <th>Status</th>
                    <th className="right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {custJobs.map((j) => (
                    <tr key={j.id}>
                      <td>{j.type}</td>
                      <td className="muted">{j.date}{j.start ? `, ${j.start}` : ""}</td>
                      <td><StatusBadge value={j.status} /></td>
                      <td className="right num">{j.est != null ? `$${j.est}` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card title="Conversations" icon="Chat" padded={false}>
            {custConvs.length === 0 ? (
              <div className="empty" style={{ padding: 14 }}>No conversations yet.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column" }}>
                {custConvs.map((c) => (
                  <div key={c.id} style={{
                    padding: "12px 16px",
                    borderBottom: "1px solid var(--divider)",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <Channel kind={c.channel} />
                      <span className="mono muted" style={{ fontSize: 11.5 }}>{c.started_at}</span>
                      {c.booked && (
                        <span className="status completed" style={{ fontSize: 10.5, marginLeft: "auto" }}>
                          <span className="dot" /> Booked
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.5 }}>{c.preview}</div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

function Stat({ label, value, mono = true }) {
  return (
    <div>
      <div style={{ fontSize: 10.5, color: "var(--text-subtle)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
        {label}
      </div>
      <div className={mono ? "tnum" : ""} style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em" }}>{value}</div>
    </div>
  );
}
