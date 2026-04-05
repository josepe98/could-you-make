import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { submitTicket } from '../api.js'

const APPS = [
  { value: 'life-folio', label: 'Life Folio' },
  { value: 'canopy', label: 'Canopy' },
  { value: 'kno', label: 'KNO Mgmt' },
  { value: 'practice-profiles', label: 'Practice Profiles' },
  { value: 'delta-mqds', label: 'delta-mqds' },
  { value: 'sampras', label: 'Sampras' },
]

const APP_LABELS = Object.fromEntries(APPS.map(a => [a.value, a.label]))

export default function Submit() {
  const [params] = useSearchParams()
  const presetApp = params.get('app') || ''

  const [form, setForm] = useState({
    app: presetApp,
    type: 'Bug',
    title: '',
    description: '',
    submitter_urgency: 'Medium',
    submitter_email: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const payload = { ...form }
      if (!payload.submitter_email) delete payload.submitter_email
      const data = await submitTicket(payload)
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (result) {
    return (
      <div className="page">
        <div className="card">
          <div className="success-box">
            <h2>✓ Submitted</h2>
            <p style={{ marginTop: 8, fontWeight: 600, fontSize: '1.1rem' }}>{result.display_id}</p>
            <p style={{ marginTop: 4, color: 'var(--text-muted)' }}>{result.message}</p>
            {form.submitter_email && (
              <p style={{ marginTop: 8, fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                A confirmation has been sent to {form.submitter_email}.
              </p>
            )}
            <p style={{ marginTop: 16, fontSize: '0.875rem' }}>
              <a href={`/ticket/${result.lookup_token}`}>Track status →</a>
            </p>
          </div>
          <button className="btn btn-secondary" style={{ marginTop: 20 }} onClick={() => { setResult(null); setForm(f => ({ ...f, title: '', description: '', submitter_email: '' })) }}>
            Submit another
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="card">
        <h1>Could You Make…</h1>
        <p className="subtitle">Found something that doesn't work? Or have a great idea for improvements? Fill out the details below and Erik will get right on it!</p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>App</label>
            <select
              value={form.app}
              onChange={e => set('app', e.target.value)}
              disabled={!!presetApp}
              required
            >
              <option value="">Select an app…</option>
              {APPS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label>Type</label>
            <select value={form.type} onChange={e => set('type', e.target.value)} required>
              <option>Bug</option>
              <option>Enhancement</option>
              <option>Question</option>
            </select>
          </div>

          <div className="form-group">
            <label>Title</label>
            <input
              type="text"
              value={form.title}
              onChange={e => set('title', e.target.value)}
              placeholder="Short summary…"
              required
            />
          </div>

          <div className="form-group">
            <label>Description</label>
            <textarea
              value={form.description}
              onChange={e => set('description', e.target.value)}
              placeholder="Steps to reproduce, expected vs actual, etc."
              required
            />
          </div>

          <div className="form-group">
            <label>Urgency</label>
            <select value={form.submitter_urgency} onChange={e => set('submitter_urgency', e.target.value)}>
              <option>Low</option>
              <option>Medium</option>
              <option>High</option>
            </select>
          </div>

          <div className="form-group">
            <label>Email <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>(optional)</span></label>
            <input
              type="email"
              value={form.submitter_email}
              onChange={e => set('submitter_email', e.target.value)}
              placeholder="you@example.com"
            />
            <p className="hint">Receive a confirmation with your ticket ID and status link.</p>
          </div>

          {error && <p className="error">{error}</p>}

          <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: '100%', justifyContent: 'center' }}>
            {submitting ? 'Submitting…' : 'Submit ticket'}
          </button>
        </form>
        <p style={{ textAlign: 'center', marginTop: 20, fontSize: '0.8rem' }}>
          <a href="/admin" style={{ color: 'var(--text-muted)' }}>Admin →</a>
        </p>
      </div>
    </div>
  )
}
