
const BASE = import.meta.env.VITE_API_BASE || "/api";

async function get(path, token) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(BASE + path, { headers });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}

async function post(path, token) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(BASE + path, { method: "POST", headers });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json();
}

export async function fetchAuthMe(token) {
  const res = await fetch(BASE + "/auth/me", { headers: { Authorization: `Bearer ${token}` } });
  if (res.status === 404 || res.status === 403) return null;
  if (!res.ok) throw new Error(`GET /auth/me → ${res.status}`);
  return res.json();
}
export async function claimBusiness(token, inviteToken) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}/auth/claim?invite_token=${encodeURIComponent(inviteToken)}`, {
    method: "POST", headers,
  });
  if (!res.ok) throw new Error(`POST /auth/claim → ${res.status}`);
  return res.json();
}
export async function fetchBusiness(token)         { return get("/businesses/me", token); }
export async function fetchTechnicians(token)      { return get("/technicians", token); }
export async function fetchJobs(token)             { return get("/jobs", token); }
export async function fetchCustomers(token)        { return get("/customers", token); }
export async function fetchConversations(token)    { return get("/conversations", token); }

export async function sendOwnerReply(token, conversationId, body) {
  const res = await fetch(`${BASE}/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ body }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`POST /conversations/${conversationId}/messages → ${res.status}: ${detail}`);
  }
  return res.json();
}
export async function fetchDashboardSummary(token) { return get("/dashboard/summary", token); }
export async function fetchDashboardFeed(token)    { return get("/dashboard/feed", token); }

export async function updateJobStatus(token, jobId, status) {
  const res = await fetch(`${BASE}/jobs/${jobId}/status?status=${encodeURIComponent(status)}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`PATCH /jobs/${jobId}/status → ${res.status}`);
  return res.json();
}

export async function createJob(token, payload) {
  const res = await fetch(`${BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`POST /jobs → ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function rescheduleJob(token, jobId, newSlotId) {
  const res = await fetch(`${BASE}/jobs/${jobId}/reschedule`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ new_slot_id: newSlotId }),
  });
  if (!res.ok) throw new Error(`PATCH /jobs/${jobId}/reschedule → ${res.status}`);
  return res.json();
}

export async function fetchAvailableSlots(token, days = 14) {
  return get(`/timeslots/available?days=${days}`, token);
}

export async function fetchAllSlots(token, days = 30) {
  return get(`/timeslots?days=${days}`, token);
}

export async function createSlot(token, payload) {
  const res = await fetch(`${BASE}/timeslots`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`POST /timeslots → ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function createSlotsBulk(token, payload) {
  const res = await fetch(`${BASE}/timeslots/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`POST /timeslots/bulk → ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function deleteSlot(token, slotId) {
  const res = await fetch(`${BASE}/timeslots/${slotId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`DELETE /timeslots/${slotId} → ${res.status}: ${detail}`);
  }
}

// --- Mutations: business + technicians ---

export async function patchBusiness(token, updates) {
  const res = await fetch(`${BASE}/businesses/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`PATCH /businesses/me → ${res.status}`);
  return res.json();
}

export async function createTechnician(token, payload) {
  const res = await fetch(`${BASE}/technicians`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`POST /technicians → ${res.status}`);
  return res.json();
}

export async function patchTechnician(token, id, updates) {
  const res = await fetch(`${BASE}/technicians/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`PATCH /technicians/${id} → ${res.status}`);
  return res.json();
}

export async function deleteTechnician(token, id) {
  const res = await fetch(`${BASE}/technicians/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`DELETE /technicians/${id} → ${res.status}`);
}
