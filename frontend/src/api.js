const BASE = '/api'

export async function submitTicket(data) {
  const res = await fetch(`${BASE}/tickets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to submit ticket')
  }
  return res.json()
}

export async function getTicket(displayId) {
  const res = await fetch(`${BASE}/tickets/${displayId}`)
  if (!res.ok) throw new Error('Ticket not found')
  return res.json()
}

export async function adminLogin(password) {
  const res = await fetch(`${BASE}/admin/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ password }),
  })
  if (!res.ok) throw new Error('Invalid password')
  return res.json()
}

export async function adminLogout() {
  await fetch(`${BASE}/admin/logout`, { method: 'POST', credentials: 'include' })
}

export async function getAdminTickets(filters = {}) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v) })
  const res = await fetch(`${BASE}/admin/tickets?${params}`, { credentials: 'include' })
  if (res.status === 401) throw new Error('Unauthorized')
  if (!res.ok) throw new Error('Failed to load tickets')
  return res.json()
}

export async function updateTicket(id, data) {
  const res = await fetch(`${BASE}/admin/tickets/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update ticket')
  return res.json()
}

export async function deleteTicket(id) {
  const res = await fetch(`${BASE}/admin/tickets/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) throw new Error('Failed to delete ticket')
  return res.json()
}

export async function listApps() {
  const res = await fetch(`${BASE}/apps`)
  if (!res.ok) throw new Error('Failed to load apps')
  return res.json()
}

export async function createApp(data) {
  const res = await fetch(`${BASE}/admin/apps`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create app')
  }
  return res.json()
}

export async function updateApp(slug, data) {
  const res = await fetch(`${BASE}/admin/apps/${slug}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update app')
  }
  return res.json()
}

export async function deleteApp(slug) {
  const res = await fetch(`${BASE}/admin/apps/${slug}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to delete app')
  }
  return res.json()
}

export async function changePassword(currentPassword, newPassword) {
  const res = await fetch(`${BASE}/admin/change-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to change password')
  }
  return res.json()
}
