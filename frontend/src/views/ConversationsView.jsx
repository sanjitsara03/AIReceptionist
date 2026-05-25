import { useEffect, useState } from 'react';
import { I } from '../icons.jsx';
import { Channel, Avatar } from '../components/Shell.jsx';
import { useData } from '../DataContext.jsx';
import { sendOwnerReply } from '../api.js';

export function ConversationsView({ focusConversationId, onOpenCustomer }) {
  const { data, reload, getToken } = useData();
  const { conversations, customers } = data;
  const [selected, setSelected] = useState(focusConversationId ?? conversations[0]?.id ?? null);
  const [filter, setFilter] = useState("all");
  const [refreshing, setRefreshing] = useState(false);

  // If the parent navigates here via global search, jump to that conversation.
  useEffect(() => {
    if (focusConversationId != null) setSelected(focusConversationId);
  }, [focusConversationId]);

  const onRefresh = async () => {
    setRefreshing(true);
    try { await reload(); } finally { setRefreshing(false); }
  };

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
          <button className="btn ghost" onClick={onRefresh} disabled={refreshing}>
            <I.Refresh /> {refreshing ? "Refreshing…" : "Refresh"}
          </button>
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
              <button
                className="btn"
                onClick={() => cust && onOpenCustomer?.(cust.id)}
                disabled={!cust}
              >
                <I.User /> Open customer
              </button>
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

          {conv.channel === "sms" && (
            <ReplyComposer conversationId={conv.id} getToken={getToken} reload={reload} />
          )}
        </div>
      </div>
    </>
  );
}

// SMS reply composer pinned below the thread. Owner-typed messages send as
// real Twilio SMS from the business's number → the customer's phone, then
// appear in the thread once `reload()` pulls them back.
function ReplyComposer({ conversationId, getToken, reload }) {
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  const send = async () => {
    const trimmed = body.trim();
    if (!trimmed) return;
    setSending(true);
    setError(null);
    try {
      const token = await getToken();
      await sendOwnerReply(token, conversationId, trimmed);
      setBody("");
      await reload();
    } catch (e) {
      setError(e.message || "Failed to send");
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      send();
    }
  };

  return (
    <div style={{
      borderTop: "1px solid var(--divider)",
      padding: "12px 16px",
      background: "var(--bg-elev)",
      display: "flex", flexDirection: "column", gap: 6,
    }}>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Reply by SMS… (⌘↵ to send)"
          rows={2}
          disabled={sending}
          style={{
            flex: 1, resize: "vertical", minHeight: 38, padding: "8px 10px",
            fontSize: 13, fontFamily: "inherit", borderRadius: 6,
            border: "1px solid var(--border)", background: "var(--bg)",
            color: "var(--text)",
          }}
        />
        <button
          className="btn primary"
          onClick={send}
          disabled={sending || !body.trim()}
          style={{ height: 38 }}
        >
          {sending ? "Sending…" : "Send SMS"}
        </button>
      </div>
      {error && (
        <div style={{ fontSize: 11.5, color: "var(--error, #e53e3e)" }}>{error}</div>
      )}
      <div style={{ fontSize: 10.5, color: "var(--text-faint)" }}>
        Sends from your business number — counts against your daily message limit.
      </div>
    </div>
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
