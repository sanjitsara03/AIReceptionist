import { useEffect } from "react";

// Public SMS terms / CTA page. Linked from the Twilio toll-free verification
// form so reviewers can confirm the opt-in disclosure. Intentionally NOT
// linked from anywhere else in the app, and tagged noindex so search engines
// don't surface it.
export function SmsTerms() {
  useEffect(() => {
    document.title = "Joe's Plumbing — SMS Terms";
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow";
    document.head.appendChild(meta);
    return () => { document.head.removeChild(meta); };
  }, []);

  const businessName = "Joe's Plumbing";
  const businessNumber = import.meta.env.VITE_TWILIO_NUMBER || "(XXX) XXX-XXXX";
  const supportEmail = "support@joesplumbing.example";

  return (
    <main style={styles.page}>
      <article style={styles.card}>
        <header style={{ marginBottom: 32 }}>
          <h1 style={styles.h1}>{businessName}</h1>
          <p style={styles.tagline}>
            24/7 residential plumbing service — drain cleaning, pipe repair, water heater install,
            leak detection, and emergency calls.
          </p>
        </header>

        <section style={styles.section}>
          <h2 style={styles.h2}>Text us to book</h2>
          <p>
            Text or call <strong style={styles.number}>{businessNumber}</strong> to schedule an
            appointment. Our AI receptionist will confirm availability, book your time slot, and
            send a 24-hour reminder before your appointment.
          </p>
        </section>

        <section style={styles.section}>
          <h2 style={styles.h2}>Sample messages you may receive</h2>
          <ul style={styles.list}>
            <li>
              <em>"Hi! This is the AI receptionist for Joe's Plumbing. How can I help you today?"</em>
            </li>
            <li>
              <em>"Booked! Your drain cleaning is confirmed for Tuesday at 2:00 PM. Reply STOP to opt out."</em>
            </li>
            <li>
              <em>"Reminder: Your plumbing appointment with Joe's Plumbing is tomorrow at 9:00 AM. Reply STOP to opt out."</em>
            </li>
          </ul>
        </section>

        <section style={styles.section}>
          <h2 style={styles.h2}>SMS Terms &amp; Opt-in</h2>
          <ul style={styles.list}>
            <li>
              By texting our number, you consent to receive SMS messages from {businessName}{" "}
              related to your appointment (booking confirmations, reminders, and scheduling changes).
            </li>
            <li>
              Message frequency varies based on your appointment activity — typically 1–4 messages
              per appointment.
            </li>
            <li>Message and data rates may apply.</li>
            <li>
              Reply <strong>STOP</strong> at any time to opt out. Reply <strong>HELP</strong> for help.
            </li>
            <li>
              For support, email{" "}
              <a href={`mailto:${supportEmail}`} style={styles.link}>
                {supportEmail}
              </a>
              .
            </li>
          </ul>
        </section>

        <section style={styles.section}>
          <h2 style={styles.h2}>Privacy</h2>
          <p>
            We collect your phone number and message content only to provide the appointment-booking
            service described above. We do not sell, rent, or share your phone number or message
            content with third parties for marketing purposes. SMS opt-out requests (<strong>STOP</strong>)
            are honored immediately and permanently.
          </p>
        </section>

        <footer style={styles.footer}>
          <p>&copy; {new Date().getFullYear()} {businessName}. All rights reserved.</p>
        </footer>
      </article>
    </main>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#fafafa",
    padding: "48px 16px",
    fontFamily: "system-ui, -apple-system, sans-serif",
    color: "#1a1a1a",
    lineHeight: 1.6,
  },
  card: {
    maxWidth: 720,
    margin: "0 auto",
    padding: "48px 56px",
    background: "#fff",
    borderRadius: 12,
    boxShadow: "0 1px 3px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.04)",
  },
  h1: { fontSize: 32, fontWeight: 700, margin: 0, marginBottom: 8 },
  h2: { fontSize: 18, fontWeight: 600, margin: 0, marginBottom: 12, marginTop: 0 },
  tagline: { color: "#555", fontSize: 15, margin: 0 },
  section: { marginBottom: 28 },
  number: { fontSize: 18, color: "#1a1a1a" },
  list: { paddingLeft: 20, margin: 0 },
  link: { color: "#2563eb", textDecoration: "underline" },
  footer: {
    marginTop: 40,
    paddingTop: 24,
    borderTop: "1px solid #eee",
    fontSize: 13,
    color: "#888",
  },
};
