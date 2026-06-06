import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getTicket, getPublicMessages, sendPublicMessage } from '../api.js'
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
  const [messages, setMessages] = useState([])
  const [messagesError, setMessagesError] = useState(null)
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const [replyError, setReplyError] = useState(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      getTicket(token),
      getPublicMessages(token).catch(e => { setMessagesError(e.message); return [] }),
    ])
      .then(([t, ms]) => {
        if (cancelled) return
        setTicket(t)
        setMessages(ms)
      })
      .catch(() => { if (!cancelled) setError('Ticket not found.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [token])

  async function handleSendReply(e) {
    e.preventDefault()
    const body = reply.trim()
    if (!body) return
    setSending(true)
    setReplyError(null)
    try {
      const msg = await sendPublicMessage(token, body)
      setMessages(ms => [...ms, msg])
      setReply('')
    } catch (err) {
      setReplyError(err.message)
    } finally {
      setSending(false)
    }
  }

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

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 20, marginTop: 24 }}>
              <h2 style={{ fontSize: '1rem', marginTop: 0, marginBottom: 12 }}>Conversation</h2>
              {messagesError && (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                  Couldn't load messages: {messagesError}
                </p>
              )}
              {!messagesError && messages.length === 0 && (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', fontStyle: 'italic' }}>
                  No messages yet. Use the form below to send a note about your ticket.
                </p>
              )}
              {messages.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                  {messages.map(m => (
                    <div
                      key={m.id}
                      style={{
                        background: m.direction === 'admin' ? '#e8f0fe' : '#f6f6f3',
                        borderLeft: `3px solid ${m.direction === 'admin' ? '#2563eb' : '#6b6b65'}`,
                        padding: '10px 14px',
                        borderRadius: 4,
                        fontSize: '0.9rem',
                      }}
                    >
                      <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--text-muted)', marginBottom: 4 }}>
                        {m.direction === 'admin' ? 'Erik' : 'You'}
                        {' · '}
                        {new Date(m.created_at).toLocaleString()}
                      </div>
                      <div style={{ whiteSpace: 'pre-wrap' }}>{m.body}</div>
                    </div>
                  ))}
                </div>
              )}

              <form onSubmit={handleSendReply}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 600, fontSize: '0.875rem' }}>
                  Your reply
                </label>
                <textarea
                  value={reply}
                  onChange={e => setReply(e.target.value)}
                  placeholder="Type your response or any additional context…"
                  style={{ width: '100%', minHeight: 100 }}
                  disabled={sending}
                />
                {replyError && <p className="error" style={{ marginTop: 4 }}>{replyError}</p>}
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={sending || !reply.trim()}
                  >
                    {sending ? 'Sending…' : 'Send reply'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
