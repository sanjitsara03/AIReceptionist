// Admin-API fetch helpers. Auth is X-Admin-Secret stored in localStorage.

const BASE = import.meta.env.VITE_API_BASE || "/api";
const SECRET_KEY = "adminSecret";

export function storedSecret() {
  return localStorage.getItem(SECRET_KEY) || "";
}

export function storeSecret(s) {
  localStorage.setItem(SECRET_KEY, s);
}

export function clearSecret() {
  localStorage.removeItem(SECRET_KEY);
}

function headers() {
  return { "X-Admin-Secret": storedSecret() };
}

async function jreq(method, path, body) {
  const opts = { method, headers: { ...headers() } };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(BASE + path, opts);
  return res;
}

// --- Businesses ---

export async function listBusinesses() {
  const res = await jreq("GET", "/admin/businesses");
  if (!res.ok) throw Object.assign(new Error(`listBusinesses ${res.status}`), { status: res.status });
  return res.json();
}

export async function createBusiness(payload) {
  const res = await jreq("POST", "/admin/businesses", payload);
  if (!res.ok) {
    const detail = await res.text();
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return res.json();
}

export async function deleteBusiness(id) {
  const res = await jreq("DELETE", `/admin/businesses/${id}`);
  if (!res.ok) throw Object.assign(new Error(`deleteBusiness ${res.status}`), { status: res.status });
}

// --- Invites ---

export async function listInvites(businessId) {
  const res = await jreq("GET", `/admin/invites?business_id=${businessId}`);
  if (!res.ok) throw Object.assign(new Error(`listInvites ${res.status}`), { status: res.status });
  return res.json();
}

export async function createInvite(businessId, days = 7) {
  // Uses the existing public POST /invites endpoint (also admin-secret-gated)
  const res = await fetch(
    `${BASE}/invites?business_id=${businessId}&expires_in_days=${days}`,
    { method: "POST", headers: headers() },
  );
  if (!res.ok) throw Object.assign(new Error(`createInvite ${res.status}`), { status: res.status });
  return res.json();
}
