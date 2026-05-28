// Soft top banner shown on every dashboard view. Used to communicate a
// known limitation (e.g., SMS deliverability paused while Twilio
// verification is pending). Controlled by VITE_SMS_BANNER so it can be
// flipped on or off with a Railway redeploy, no code change required.

export function SmsBanner() {
  const enabled = import.meta.env.VITE_SMS_BANNER === "true";
  if (!enabled) return null;

  const phone = import.meta.env.VITE_TWILIO_NUMBER || "";
  const phoneText = phone ? ` Please call ${formatPhone(phone)} to test the AI.` : "";

  return (
    <div role="status" style={styles.wrap}>
      <span style={styles.icon} aria-hidden="true">ⓘ</span>
      <span>
        <strong>Voice fully operational.</strong> SMS replies are paused while
        Twilio verification is in progress.{phoneText}
      </span>
    </div>
  );
}

function formatPhone(e164) {
  // +18445931325 → (844) 593-1325
  const digits = e164.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  return e164;
}

const styles = {
  wrap: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 20px",
    background: "#fef3c7",
    color: "#92400e",
    borderBottom: "1px solid #fde68a",
    fontSize: 13,
    lineHeight: 1.5,
    fontFamily: "system-ui, -apple-system, sans-serif",
  },
  icon: {
    fontSize: 16,
    lineHeight: 1,
    flexShrink: 0,
  },
};
