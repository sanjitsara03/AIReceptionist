import { useState } from 'react';
import { I } from '../icons.jsx';
import { Channel, Avatar } from '../components/Shell.jsx';
import { useData } from '../DataContext.jsx';

export function ConversationsView() {
  const { data } = useData();
  const { conversations, customers } = data;
  const [selected, setSelected] = useState(conversations[0]?.id ?? null);
  const [filter, setFilter] = useState("all");

  if (conversations.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-subtle)" }}>
        <h1 style={{ fontSize: 18, marginBottom: 8 }}>No conversations yet</h1>
        <p style={{ fontSize: 13 }}>When customers text or call, their conversations will appear here.</p>
      </div>
    );
  }

  const byCust = (id) => customers.find((c) => c.id === id);

  const filtered = conversations.filter((c) => {
    if (filter === "all") return true;
    if (filter === "voice") return c.channel === "voice";
    if (filter === "sms") return c.channel === "sms";
    if (filter === "booked") return c.booked;
    if (filter === "unresolved") return !c.booked;
    return true;
  });

  const conv = conversations.find((c) => c.id === selected) || conversations[0];
  const cust = byCust(conv.customer_id);

  return (
    <>
      <div className="content-header">
        <div className="content-title-block">
          <h1>Conversations</h1>
          <p>SMS and voice transcripts handled by the AI receptionist.</p>
        </div>
        <div className="row-flex">
          <button className="btn ghost"><I.Refresh /> Refresh</button>
          <button className="btn"><I.Download /> Export</button>
        </div>
      </div>

      <div className="conv-layout">
        <div className="conv-list">
          <div className="conv-list-header">
            <div className="pill-group">
              {["all", "voice", "sms", "booked", "unresolved"].map((f) => (
                <button key={f} className={"pill " + (filter === f ? "active" : "")} onClick={() => setFilter(f)}>
                  {f === "unresolved" ? "Open" : f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <div className="conv-list-scroll">
            {filtered.map((c) => {
              const cu = byCust(c.customer_id);
              return (
                <div
                  key={c.id}
                  className={"conv-row" + (selected === c.id ? " selected" : "")}
                  onClick={() => setSelected(c.id)}
                >
                  <div className="conv-name">
                    {c.unread && <span className="conv-unread" />} {cu?.name}
                  </div>
                  <div className="conv-time">{c.last_at}</div>
                  <div className="conv-preview">{c.preview}</div>
                  <div className="conv-channel-row">
                    <Channel kind={c.channel} />
                    {c.duration && <span className="mono" style={{ fontSize: 11, color: "var(--text-faint)" }}>· {c.duration}</span>}
                    {c.booked ? (
                      <span className="status completed" style={{ marginLeft: "auto", fontSize: 10.5 }}>
                        <span className="dot" /> Booked
                      </span>
                    ) : (
                      <span className="status pending" style={{ marginLeft: "auto", fontSize: 10.5 }}>
                        <span className="dot" /> Open
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="conv-detail">
          <div className="conv-detail-header">
            <Avatar name={cust?.name || "?"} size={36} />
            <div className="who">
              <div className="name">{cust?.name}</div>
              <div className="ph">{cust?.phone}</div>
            </div>
            <span style={{ marginLeft: 16 }}><Channel kind={conv.channel} /></span>
            <span className="mono muted" style={{ fontSize: 12, marginLeft: 8 }}>
              {conv.started_at}
              {conv.duration && <> · {conv.duration}</>}
            </span>
            <div className="h-actions">
              <button className="btn ghost"><I.Phone /> Call back</button>
              <button className="btn"><I.User /> Open customer</button>
            </div>
          </div>

          <div className="conv-thread">
            <div className="thread-separator">
              <span>{conv.started_at}</span>
            </div>
            {conv.messages.map((m, i) => {
              if (m.tool) {
                return (
                  <div key={i} className="tool-call">
                    <I.Wand />
                    <span className="mono">{m.tool}(</span>
                    <span className="val">{m.args || "…"}</span>
                    <span className="mono">)</span>
                    <span className="arrow">→</span>
                    <span>{m.result}</span>
                    <span className="mono" style={{ marginLeft: 6, color: "var(--text-faint)" }}>· {m.time}</span>
                  </div>
                );
              }
              if (conv.channel === "voice") {
                return <VoiceBubble key={i} msg={m} />;
              }
              return (
                <div key={i} className="bubble-group" style={{ display: "flex", flexDirection: "column" }}>
                  <div className={"bubble " + (m.dir === "out" ? "out" : "in")}>{m.body}</div>
                  <div className={"bubble-time " + (m.dir === "out" ? "out" : "in")}>{m.time}{m.dir === "out" && " · AI"}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}

function VoiceBubble({ msg }) {
  const isOut = msg.dir === "out";
  const seed = msg.body.length;
  const bars = Array.from({ length: 28 }, (_, i) => 4 + ((seed * (i + 3)) % 13));
  return (
    <div className={"voice-bubble " + (isOut ? "out" : "")}>
      <div className="voice-meta">
        {isOut ? <I.Bot /> : <I.Mic />}
        <span>{isOut ? "AI · Polly.Joanna" : "Caller"}</span>
        <span style={{ marginLeft: "auto" }}>{msg.time}</span>
      </div>
      <div className="voice-waveform">
        {bars.map((h, i) => (
          <span
            key={i}
            className="bar"
            style={{ height: h + "px", background: isOut ? "var(--accent)" : "var(--text-faint)" }}
          />
        ))}
      </div>
      <div style={{ fontSize: 13, color: isOut ? "var(--accent)" : "var(--text)" }}>
        {msg.body}
      </div>
    </div>
  );
}
