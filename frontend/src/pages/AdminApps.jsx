import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listApps, createApp, updateApp, deleteApp } from '../api.js'
import { useApps } from '../AppsContext.jsx'
import { useConfirm } from '../ConfirmDialog.jsx'

const EMPTY_NEW = { slug: '', label: '', prefix: '', display_order: 0 }

export default function AdminApps() {
  const navigate = useNavigate()
  const { refresh: refreshContext } = useApps()
  const confirm = useConfirm()
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [newApp, setNewApp] = useState(EMPTY_NEW)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [pendingEdits, setPendingEdits] = useState({})
  const [busySlug, setBusySlug] = useState(null)
  const [rowError, setRowError] = useState({})

  async function loadApps() {
    setLoading(true)
    try {
      const data = await listApps()
      setApps(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadApps() }, [])

  const setEdit = (slug, field, value) => {
    setPendingEdits(e => ({ ...e, [slug]: { ...(e[slug] || {}), [field]: value } }))
  }

  async function handleCreate(e) {
    e.preventDefault()
    setCreating(true)
    setCreateError(null)
    try {
      await createApp({
        slug: newApp.slug.trim(),
        label: newApp.label.trim(),
        prefix: newApp.prefix.trim().toUpperCase(),
        display_order: Number(newApp.display_order) || 0,
      })
      setNewApp(EMPTY_NEW)
      await loadApps()
      refreshContext()
    } catch (err) {
      setCreateError(err.message)
    } finally {
      setCreating(false)
    }
  }

  async function handleSave(slug) {
    const edits = pendingEdits[slug]
    if (!edits) return
    const original = apps.find(a => a.slug === slug)
    if (edits.prefix !== undefined && edits.prefix !== original.prefix) {
      const ok = await confirm({
        title: 'Change prefix?',
        body: `Changing the prefix from "${original.prefix}" to "${edits.prefix}" will change the display IDs of every ticket in this app.\n\nBookmarked status URLs still work (they use lookup tokens), but subject lines in old confirmation emails will no longer match.`,
        confirmLabel: 'Change prefix',
      })
      if (!ok) return
    }
    setBusySlug(slug)
    setRowError(e => ({ ...e, [slug]: null }))
    try {
      const payload = {}
      if (edits.label !== undefined) payload.label = edits.label.trim()
      if (edits.prefix !== undefined) payload.prefix = edits.prefix.trim().toUpperCase()
      if (edits.display_order !== undefined) payload.display_order = Number(edits.display_order) || 0
      await updateApp(slug, payload)
      setPendingEdits(e => { const next = { ...e }; delete next[slug]; return next })
      await loadApps()
      refreshContext()
    } catch (err) {
      setRowError(e => ({ ...e, [slug]: err.message }))
    } finally {
      setBusySlug(null)
    }
  }

  async function handleDelete(slug, label) {
    const ok = await confirm({
      title: `Delete "${label}"?`,
      body: `Slug: ${slug}\n\nThis cannot be undone. Apps with tickets cannot be deleted.`,
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    setBusySlug(slug)
    setRowError(e => ({ ...e, [slug]: null }))
    try {
      await deleteApp(slug)
      await loadApps()
      refreshContext()
    } catch (err) {
      setRowError(e => ({ ...e, [slug]: err.message }))
    } finally {
      setBusySlug(null)
    }
  }

  if (loading) {
    return <div className="page"><div className="card"><p className="loading">Loading apps…</p></div></div>
  }
  if (error === 'Unauthorized') {
    navigate('/admin/login')
    return null
  }

  return (
    <div className="page" style={{ alignItems: 'flex-start', paddingTop: 32 }}>
      <div className="card card-wide" style={{ maxWidth: 900 }}>
        <div className="admin-header">
          <div>
            <h1>Apps</h1>
            <p className="subtitle" style={{ marginBottom: 0 }}>
              Manage the apps that can submit tickets. Slugs are permanent; labels, prefixes, and ordering can be edited.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => navigate('/admin')}>← Dashboard</button>
          </div>
        </div>

        {error && error !== 'Unauthorized' && <p className="error" style={{ marginTop: 16 }}>{error}</p>}

        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
              <th style={{ padding: '8px 12px 8px 0' }}>Slug</th>
              <th style={{ padding: '8px 12px' }}>Label</th>
              <th style={{ padding: '8px 12px', width: 120 }}>Prefix</th>
              <th style={{ padding: '8px 12px', width: 96 }}>Order</th>
              <th style={{ padding: '8px 0', width: 180 }}></th>
            </tr>
          </thead>
          <tbody>
            {apps.map(a => {
              const edit = pendingEdits[a.slug] || {}
              const hasEdits = Object.keys(edit).length > 0
              const label = edit.label ?? a.label
              const prefix = edit.prefix ?? a.prefix
              const order = edit.display_order ?? a.display_order
              return (
                <tr key={a.slug} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '10px 12px 10px 0' }}>
                    <code style={{ fontSize: '0.85rem' }}>{a.slug}</code>
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <input
                      type="text"
                      value={label}
                      onChange={e => setEdit(a.slug, 'label', e.target.value)}
                      style={{ width: '100%' }}
                    />
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <input
                      type="text"
                      value={prefix}
                      onChange={e => setEdit(a.slug, 'prefix', e.target.value)}
                      maxLength={8}
                      style={{ width: '100%', textTransform: 'uppercase' }}
                    />
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <input
                      type="number"
                      value={order}
                      onChange={e => setEdit(a.slug, 'display_order', e.target.value)}
                      style={{ width: '100%' }}
                    />
                  </td>
                  <td style={{ padding: '10px 0', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => handleSave(a.slug)}
                        disabled={!hasEdits || busySlug === a.slug}
                      >
                        Save
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleDelete(a.slug, a.label)}
                        disabled={busySlug === a.slug}
                      >
                        Delete
                      </button>
                    </div>
                    {rowError[a.slug] && (
                      <p className="error" style={{ margin: '6px 0 0', fontSize: '0.8rem' }}>{rowError[a.slug]}</p>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        <form onSubmit={handleCreate} style={{ marginTop: 24, padding: 16, border: '1px solid var(--border)', borderRadius: 8 }}>
          <h3 style={{ marginTop: 0 }}>Add a new app</h3>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div className="form-group" style={{ margin: 0, flex: '2 1 200px', minWidth: 0 }}>
              <label style={{ fontSize: '0.8rem' }}>Slug <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>(lowercase, permanent)</span></label>
              <input
                type="text"
                value={newApp.slug}
                onChange={e => setNewApp(a => ({ ...a, slug: e.target.value.toLowerCase() }))}
                placeholder="my-app"
                pattern="[a-z0-9][a-z0-9-]*"
                required
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div className="form-group" style={{ margin: 0, flex: '2 1 200px', minWidth: 0 }}>
              <label style={{ fontSize: '0.8rem' }}>Label</label>
              <input
                type="text"
                value={newApp.label}
                onChange={e => setNewApp(a => ({ ...a, label: e.target.value }))}
                placeholder="My App"
                required
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div className="form-group" style={{ margin: 0, flex: '0 0 120px' }}>
              <label style={{ fontSize: '0.8rem' }}>Prefix</label>
              <input
                type="text"
                value={newApp.prefix}
                onChange={e => setNewApp(a => ({ ...a, prefix: e.target.value.toUpperCase() }))}
                placeholder="MYA"
                maxLength={8}
                pattern="[A-Z0-9]+"
                required
                style={{ width: '100%', boxSizing: 'border-box', textTransform: 'uppercase' }}
              />
            </div>
            <div className="form-group" style={{ margin: 0, flex: '0 0 96px' }}>
              <label style={{ fontSize: '0.8rem' }}>Order</label>
              <input
                type="number"
                value={newApp.display_order}
                onChange={e => setNewApp(a => ({ ...a, display_order: e.target.value }))}
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>
          </div>
          {createError && <p className="error" style={{ marginTop: 12 }}>{createError}</p>}
          <button type="submit" className="btn btn-primary" disabled={creating} style={{ marginTop: 12 }}>
            {creating ? 'Creating…' : 'Create app'}
          </button>
        </form>
      </div>
    </div>
  )
}
