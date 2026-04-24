import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAdminTickets, updateTicket, deleteTicket, adminLogout, changePassword } from '../api.js'
import { useApps } from '../AppsContext.jsx'
import { useConfirm } from '../ConfirmDialog.jsx'

// Temporarily hide the admin Priority column to give Title more room.
// All infrastructure (model field, API, detail drawer) is intact — flip
// this back to true to restore the column.
const SHOW_PRIORITY_COLUMN = false

const STATUS_BADGE = {
  'Open': 'badge-open',
  'In Progress': 'badge-in-progress',
  'Done': 'badge-done',
  "Won't Fix": 'badge-wont-fix',
}

const PRIORITY_BADGE = {
  'Low': 'badge-low',
  'Medium': 'badge-medium',
  'High': 'badge-high',
  'Critical': 'badge-critical',
}

// Resizable column widths (pixels). Defaults are tuned so the longest
// label in each column ("Practice Profiles", "Enhancement", etc.) fits
// without wrapping. Persisted per browser via localStorage.
const DEFAULT_COL_WIDTHS = {
  id: 88,
  app: 144,
  type: 112,
  title: 380,
  urgency: 96,
  status: 132,
  date: 100,
  actions: 88,
}
const COL_WIDTH_STORAGE_KEY = 'cym.adminColWidths.v1'

function loadColWidths() {
  if (typeof window === 'undefined') return DEFAULT_COL_WIDTHS
  try {
    const raw = window.localStorage.getItem(COL_WIDTH_STORAGE_KEY)
    if (!raw) return DEFAULT_COL_WIDTHS
    return { ...DEFAULT_COL_WIDTHS, ...JSON.parse(raw) }
  } catch {
    return DEFAULT_COL_WIDTHS
  }
}

function ResizeHandle({ onMouseDown }) {
  return (
    <span
      onMouseDown={onMouseDown}
      onClick={e => e.stopPropagation()}
      title="Drag to resize"
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        bottom: 0,
        width: 8,
        cursor: 'col-resize',
        userSelect: 'none',
      }}
    />
  )
}

function SortHeader({ label, field, sortBy, sortDir, onSort, onResize }) {
  const active = sortBy === field
  const arrow = active ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''
  return (
    <th className="sortable" style={{ position: 'relative' }} onClick={() => onSort(field)}>
      {label}{arrow}
      {onResize && <ResizeHandle onMouseDown={onResize} />}
    </th>
  )
}

export default function AdminDashboard() {
  const navigate = useNavigate()
  const { apps, appLabels } = useApps()
  const confirm = useConfirm()
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [editDraft, setEditDraft] = useState(null)
  const [saving, setSaving] = useState(false)

  const [filters, setFilters] = useState({ app: '', type: '', status: '' })
  const [sortBy, setSortBy] = useState('created_at')
  const [sortDir, setSortDir] = useState('desc')

  const [colWidths, setColWidths] = useState(loadColWidths)
  useEffect(() => {
    try { window.localStorage.setItem(COL_WIDTH_STORAGE_KEY, JSON.stringify(colWidths)) } catch {}
  }, [colWidths])
  const startResize = useCallback((colId) => (e) => {
    e.preventDefault()
    e.stopPropagation()
    const startX = e.clientX
    const startWidth = colWidths[colId]
    function onMove(ev) {
      const next = Math.max(40, startWidth + (ev.clientX - startX))
      setColWidths(w => ({ ...w, [colId]: next }))
    }
    function onUp() {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
    }
    document.body.style.cursor = 'col-resize'
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [colWidths])

  const [showPwForm, setShowPwForm] = useState(false)
  const [pwForm, setPwForm] = useState({ current: '', next: '', confirm: '' })
  const [pwError, setPwError] = useState(null)
  const [pwSuccess, setPwSuccess] = useState(false)
  const [pwSaving, setPwSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAdminTickets({ ...filters, sort_by: sortBy, sort_dir: sortDir })
      setTickets(data)
    } catch (err) {
      if (err.message === 'Unauthorized') navigate('/admin/login')
      else setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filters, sortBy, sortDir, navigate])

  useEffect(() => { load() }, [load])

  function handleSort(field) {
    if (sortBy === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(field); setSortDir('desc') }
  }

  function setFilter(k, v) {
    setFilters(f => ({ ...f, [k]: v }))
  }

  async function handleInlineChange(ticket, field, value) {
    try {
      const updated = await updateTicket(ticket.id, { [field]: value })
      const apply = () => {
        setTickets(ts => ts.map(t => t.id === updated.id ? updated : t))
        if (selected?.id === updated.id) setSelected(updated)
      }
      // Animate row sliding between section tables when status changes,
      // using the View Transitions API.
      const crossed =
        field === 'status' &&
        ticket.status !== updated.status &&
        typeof document !== 'undefined' &&
        typeof document.startViewTransition === 'function'
      if (crossed) {
        document.startViewTransition(() => {
          apply()
        })
      } else {
        apply()
      }
    } catch (e) {
      alert('Failed to update: ' + e.message)
    }
  }

  function openDetail(ticket) {
    setSelected(ticket)
    setEditDraft({ ...ticket })
  }

  async function saveDetail() {
    setSaving(true)
    try {
      const updated = await updateTicket(selected.id, {
        title: editDraft.title,
        description: editDraft.description,
        type: editDraft.type,
        admin_priority: editDraft.admin_priority || null,
        status: editDraft.status,
      })
      setTickets(ts => ts.map(t => t.id === updated.id ? updated : t))
      setSelected(updated)
      setEditDraft({ ...updated })
    } catch (e) {
      alert('Failed to save: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(ticket) {
    const ok = await confirm({
      title: `Delete ${ticket.display_id}?`,
      body: `"${ticket.title}"\n\nThis cannot be undone.`,
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    try {
      await deleteTicket(ticket.id)
      setTickets(ts => ts.filter(t => t.id !== ticket.id))
      if (selected?.id === ticket.id) setSelected(null)
    } catch (e) {
      alert('Failed to delete: ' + e.message)
    }
  }

  async function handleLogout() {
    await adminLogout()
    navigate('/admin/login')
  }

  async function handleChangePassword(e) {
    e.preventDefault()
    setPwError(null)
    setPwSuccess(false)
    if (pwForm.next !== pwForm.confirm) {
      setPwError('New passwords do not match')
      return
    }
    if (pwForm.next.length < 8) {
      setPwError('New password must be at least 8 characters')
      return
    }
    setPwSaving(true)
    try {
      await changePassword(pwForm.current, pwForm.next)
      setPwSuccess(true)
      setPwForm({ current: '', next: '', confirm: '' })
      setTimeout(() => { setShowPwForm(false); setPwSuccess(false) }, 2000)
    } catch (err) {
      setPwError(err.message)
    } finally {
      setPwSaving(false)
    }
  }

  const displayId = t => t.display_id || `CYM-${String(t.id).padStart(3, '0')}`

  const inProgressTickets = tickets.filter(t => t.status === 'In Progress')
  const openTickets = tickets.filter(t => t.status === 'Open')
  const closedTickets = tickets.filter(t => t.status === 'Done' || t.status === "Won't Fix")

  const renderRow = (t) => (
    <tr
      key={t.id}
      style={{ cursor: 'pointer', viewTransitionName: `ticket-row-${t.id}` }}
    >
      <td onClick={() => openDetail(t)}><code style={{ fontSize: '0.8rem' }}>{displayId(t)}</code></td>
      <td onClick={() => openDetail(t)}>{appLabels[t.app] || t.app}</td>
      <td onClick={() => openDetail(t)}>{t.type}</td>
      <td onClick={() => openDetail(t)}>{t.title}</td>
      <td onClick={() => openDetail(t)}>
        <span className={`badge ${PRIORITY_BADGE[t.submitter_urgency] || ''}`}>{t.submitter_urgency}</span>
      </td>
      {SHOW_PRIORITY_COLUMN && (
        <td onClick={e => e.stopPropagation()}>
          <select
            value={t.admin_priority || ''}
            onChange={e => handleInlineChange(t, 'admin_priority', e.target.value || null)}
          >
            <option value="">—</option>
            <option>Low</option>
            <option>Medium</option>
            <option>High</option>
            <option>Critical</option>
          </select>
        </td>
      )}
      <td onClick={e => e.stopPropagation()}>
        <select
          value={t.status}
          onChange={e => handleInlineChange(t, 'status', e.target.value)}
        >
          <option>Open</option>
          <option value="In Progress">In Progress</option>
          <option>Done</option>
          <option value="Won't Fix">Won't Fix</option>
        </select>
      </td>
      <td onClick={() => openDetail(t)} style={{ color: 'var(--text-muted)', fontSize: '0.8125rem', whiteSpace: 'nowrap' }}>
        {new Date(t.created_at).toLocaleDateString()}
      </td>
      <td>
        <button className="btn btn-danger btn-sm" onClick={e => { e.stopPropagation(); handleDelete(t) }}>Delete</button>
      </td>
    </tr>
  )

  const renderTable = (rows, emptyMessage) => (
    <div className="table-wrap">
      <table style={{ tableLayout: 'fixed' }}>
        <colgroup>
          <col style={{ width: colWidths.id }} />
          <col style={{ width: colWidths.app }} />
          <col style={{ width: colWidths.type }} />
          <col style={{ width: colWidths.title }} />
          <col style={{ width: colWidths.urgency }} />
          {SHOW_PRIORITY_COLUMN && <col />}
          <col style={{ width: colWidths.status }} />
          <col style={{ width: colWidths.date }} />
          <col style={{ width: colWidths.actions }} />
        </colgroup>
        <thead>
          <tr>
            <th style={{ position: 'relative' }}>ID<ResizeHandle onMouseDown={startResize('id')} /></th>
            <th style={{ position: 'relative' }}>App<ResizeHandle onMouseDown={startResize('app')} /></th>
            <th style={{ position: 'relative' }}>Type<ResizeHandle onMouseDown={startResize('type')} /></th>
            <th style={{ position: 'relative' }}>Title<ResizeHandle onMouseDown={startResize('title')} /></th>
            <SortHeader label="Urgency" field="submitter_urgency" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} onResize={startResize('urgency')} />
            {SHOW_PRIORITY_COLUMN && (
              <SortHeader label="Priority" field="admin_priority" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
            )}
            <SortHeader label="Status" field="status" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} onResize={startResize('status')} />
            <SortHeader label="Date" field="created_at" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} onResize={startResize('date')} />
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr><td colSpan={SHOW_PRIORITY_COLUMN ? 9 : 8} className="empty">{emptyMessage}</td></tr>
          )}
          {rows.map(renderRow)}
        </tbody>
      </table>
    </div>
  )

  return (
    <div className="page" style={{ alignItems: 'flex-start', paddingTop: 32 }}>
      <div className="card card-wide" style={{ maxWidth: 1400 }}>
        <div className="admin-header">
          <div>
            <h1>Could You Make</h1>
            <p className="subtitle" style={{ marginBottom: 0 }}>Admin dashboard · {tickets.length} ticket{tickets.length !== 1 ? 's' : ''}</p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => navigate('/admin/apps')}>
              Manage apps
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => { setShowPwForm(f => !f); setPwError(null); setPwSuccess(false) }}>
              {showPwForm ? 'Cancel' : 'Change password'}
            </button>
            <button className="btn btn-secondary btn-sm" onClick={handleLogout}>Sign out</button>
          </div>
        </div>

        {showPwForm && (
          <form onSubmit={handleChangePassword} style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap', padding: '12px 0', borderBottom: '1px solid var(--border)', marginBottom: 16 }}>
            <div className="form-group" style={{ margin: 0, flex: 1, minWidth: 160 }}>
              <label style={{ fontSize: '0.8rem' }}>Current password</label>
              <input type="password" value={pwForm.current} onChange={e => setPwForm(f => ({ ...f, current: e.target.value }))} required />
            </div>
            <div className="form-group" style={{ margin: 0, flex: 1, minWidth: 160 }}>
              <label style={{ fontSize: '0.8rem' }}>New password</label>
              <input type="password" value={pwForm.next} onChange={e => setPwForm(f => ({ ...f, next: e.target.value }))} required />
            </div>
            <div className="form-group" style={{ margin: 0, flex: 1, minWidth: 160 }}>
              <label style={{ fontSize: '0.8rem' }}>Confirm new password</label>
              <input type="password" value={pwForm.confirm} onChange={e => setPwForm(f => ({ ...f, confirm: e.target.value }))} required />
            </div>
            <button type="submit" className="btn btn-primary btn-sm" disabled={pwSaving} style={{ marginBottom: 1 }}>
              {pwSaving ? 'Saving…' : 'Update'}
            </button>
            {pwError && <p className="error" style={{ width: '100%', margin: 0 }}>{pwError}</p>}
            {pwSuccess && <p style={{ width: '100%', margin: 0, color: 'green', fontSize: '0.875rem' }}>Password updated successfully.</p>}
          </form>
        )}

        <div className="filters" style={{ marginBottom: 16 }}>
          <select value={filters.app} onChange={e => setFilter('app', e.target.value)}>
            <option value="">All apps</option>
            {apps.map(a => <option key={a.slug} value={a.slug}>{a.label}</option>)}
          </select>
          <select value={filters.type} onChange={e => setFilter('type', e.target.value)}>
            <option value="">All types</option>
            <option>Bug</option>
            <option>Enhancement</option>
            <option>Question</option>
          </select>
          <select value={filters.status} onChange={e => setFilter('status', e.target.value)}>
            <option value="">All statuses</option>
            <option>Open</option>
            <option value="In Progress">In Progress</option>
            <option>Done</option>
            <option value="Won't Fix">Won't Fix</option>
          </select>
          <button className="btn btn-secondary btn-sm" onClick={load}>Refresh</button>
        </div>

        {loading && <p className="loading">Loading tickets…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && !error && (
          <>
            <h2 style={{ fontSize: '1rem', marginTop: 0, marginBottom: 8, color: 'var(--text-muted)' }}>
              In Progress · {inProgressTickets.length}
            </h2>
            {renderTable(inProgressTickets, 'No in-progress tickets.')}
            <h2 style={{ fontSize: '1rem', marginTop: 24, marginBottom: 8, color: 'var(--text-muted)' }}>
              Open · {openTickets.length}
            </h2>
            {renderTable(openTickets, 'No open tickets match the current filters.')}
            <h2 style={{ fontSize: '1rem', marginTop: 24, marginBottom: 8, color: 'var(--text-muted)' }}>
              Done or Won't Fix · {closedTickets.length}
            </h2>
            {renderTable(closedTickets, 'No completed tickets.')}
          </>
        )}
      </div>

      {/* Detail drawer */}
      {selected && editDraft && (
        <div className="drawer-overlay" onClick={() => setSelected(null)}>
          <div className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer-header">
              <div>
                <code style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{displayId(selected)}</code>
                <h2 style={{ marginBottom: 0 }}>{selected.title}</h2>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setSelected(null)}>✕</button>
            </div>

            <div className="form-group">
              <label>Title</label>
              <input type="text" value={editDraft.title} onChange={e => setEditDraft(d => ({ ...d, title: e.target.value }))} />
            </div>
            <div className="form-group">
              <label>Type</label>
              <select value={editDraft.type} onChange={e => setEditDraft(d => ({ ...d, type: e.target.value }))}>
                <option>Bug</option>
                <option>Enhancement</option>
                <option>Question</option>
              </select>
            </div>
            <div className="form-group">
              <label>Description</label>
              <textarea value={editDraft.description} onChange={e => setEditDraft(d => ({ ...d, description: e.target.value }))} style={{ minHeight: 140 }} />
            </div>
            <div className="form-group">
              <label>Admin Priority</label>
              <select value={editDraft.admin_priority || ''} onChange={e => setEditDraft(d => ({ ...d, admin_priority: e.target.value || null }))}>
                <option value="">—</option>
                <option>Low</option>
                <option>Medium</option>
                <option>High</option>
                <option>Critical</option>
              </select>
            </div>
            <div className="form-group">
              <label>Status</label>
              <select value={editDraft.status} onChange={e => setEditDraft(d => ({ ...d, status: e.target.value }))}>
                <option>Open</option>
                <option value="In Progress">In Progress</option>
                <option>Done</option>
                <option value="Won't Fix">Won't Fix</option>
              </select>
            </div>

            {selected.clarifying_notes && (
              <div className="form-group" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
                <label>Clarifying notes</label>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: '0.875rem', color: 'var(--text)', background: 'var(--bg-subtle, #f6f6f6)', padding: 12, borderRadius: 6 }}>
                  {selected.clarifying_notes}
                </div>
              </div>
            )}

            <dl className="detail-grid" style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <dt>App</dt><dd>{appLabels[selected.app] || selected.app}</dd>
              <dt>Submitter urgency</dt><dd>{selected.submitter_urgency}</dd>
              <dt>Email</dt><dd>{selected.submitter_email || <span style={{ color: 'var(--text-muted)' }}>—</span>}</dd>
              <dt>Created</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd>
              <dt>Updated</dt><dd>{new Date(selected.updated_at).toLocaleString()}</dd>
            </dl>

            <div style={{ display: 'flex', gap: 8, marginTop: 'auto', paddingTop: 16 }}>
              <button className="btn btn-primary" onClick={saveDetail} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
              <button className="btn btn-secondary" onClick={() => setSelected(null)}>Cancel</button>
              <button className="btn btn-danger btn-sm" style={{ marginLeft: 'auto' }} onClick={() => handleDelete(selected)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
