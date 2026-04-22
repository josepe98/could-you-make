import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getTicket } from '../api.js'
import { useApps } from '../AppsContext.jsx'

const STATUS_BADGE = {
  'Open': 'badge-open',
  'In Progress': 'badge-in-progress',
  'Done': 'badge-done',
  "Won't Fix": 'badge-wont-fix',
}

export default function TicketStatus() {
  const { token } = useParams()
  const { appLabels } = useApps()
  const [ticket, setTicket] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getTicket(token)
      .then(setTicket)
      .catch(() => setError('Ticket not found.'))
      .finally(() => setLoading(false))
  }, [token])

  return (
    <div className="page">
      <div className="card">
        <h1>Ticket Status</h1>
        {loading && <p className="loading">Loading…</p>}
        {error && (
          <p style={{ color: 'var(--text-muted)', marginTop: 16 }}>
            No ticket found with that ID. Make sure you have the correct link.
          </p>
        )}
        {ticket && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
              <span style={{ fontWeight: 700, fontSize: '1.1rem' }}>{ticket.display_id}</span>
              <span className={`badge ${STATUS_BADGE[ticket.status] || 'badge-open'}`}>{ticket.status}</span>
            </div>
            <dl className="detail-grid">
              <dt>Title</dt><dd>{ticket.title}</dd>
              <dt>Type</dt><dd>{ticket.type}</dd>
              <dt>App</dt><dd>{appLabels[ticket.app] || ticket.app}</dd>
              <dt>Submitted</dt><dd>{new Date(ticket.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</dd>
            </dl>
          </div>
        )}
      </div>
    </div>
  )
}
