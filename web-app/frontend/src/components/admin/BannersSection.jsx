import { useState, useEffect, useCallback, useRef } from 'react'
import { get, post, del } from '@/api/client'

const COLORS = ['blue', 'gold', 'green', 'purple', 'red']
const DURATIONS = [
  { label: '24 hours', value: 24 },
  { label: '48 hours', value: 48 },
  { label: '72 hours', value: 72 },
  { label: '1 week', value: 168 },
  { label: '2 weeks', value: 336 },
  { label: '30 days', value: 720 },
]

const EMPTY_FORM = { title: '', subtitle: '', link: '', badge: 'NEW', color: 'blue', duration: 48 }

export default function BannersSection() {
  const [banners, setBanners] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [images, setImages] = useState([])
  const [imageUrl, setImageUrl] = useState('')
  const [uploading, setUploading] = useState(false)
  const [creating, setCreating] = useState(false)
  const fileRef = useRef(null)

  const loadBanners = useCallback(() => {
    get('/api/analytics/banners')
      .then(d => { if (d.success) setBanners(d.banners) })
      .catch(console.error)
  }, [])

  useEffect(() => { loadBanners() }, [loadBanners])

  const setField = (key, val) => setForm(f => ({ ...f, [key]: val }))

  const uploadFiles = async (files) => {
    if (!files.length) return
    setUploading(true)
    const urls = []
    for (const file of files) {
      const fd = new FormData()
      fd.append('image', file)
      try {
        const r = await fetch('/api/analytics/banners/upload-image', {
          method: 'POST',
          body: fd,
          credentials: 'include',
        })
        const d = await r.json()
        if (d.success) urls.push(d.url)
        else alert('Upload failed: ' + d.error)
      } catch {
        alert('Upload failed')
      }
    }
    setImages(prev => [...prev, ...urls])
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  const addUrl = () => {
    if (!imageUrl.trim()) return
    setImages(prev => [...prev, imageUrl.trim()])
    setImageUrl('')
  }

  const removeImage = (idx) => setImages(prev => prev.filter((_, i) => i !== idx))

  const createBanner = async () => {
    if (!form.title.trim() || !form.link.trim()) {
      alert('Title and Link are required.')
      return
    }
    setCreating(true)
    const expires = new Date(Date.now() + form.duration * 3600000)
    const expiresStr = expires.toISOString().slice(0, 19).replace('T', ' ')
    try {
      const d = await post('/api/analytics/banners', {
        title: form.title.trim(),
        subtitle: form.subtitle.trim() || null,
        link: form.link.trim(),
        badge_text: form.badge.trim() || 'NEW',
        color: form.color,
        expires_at: expiresStr,
        images,
      })
      if (d.success) {
        setForm(EMPTY_FORM)
        setImages([])
        loadBanners()
      } else {
        alert('Error: ' + d.error)
      }
    } catch {
      alert('Failed to create banner')
    }
    setCreating(false)
  }

  const toggleBanner = async (id) => {
    try {
      const d = await post(`/api/analytics/banners/${id}/toggle`, {})
      if (d.success) loadBanners()
      else alert('Error: ' + d.error)
    } catch {
      alert('Failed')
    }
  }

  const deleteBanner = async (id) => {
    if (!confirm('Delete this banner?')) return
    try {
      const d = await del(`/api/analytics/banners/${id}`)
      if (d.success) loadBanners()
      else alert('Error: ' + d.error)
    } catch {
      alert('Failed')
    }
  }

  const now = new Date()

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-text-primary">Promo Banners</h2>
        <p className="text-xs text-text-muted">Manage home page promotional banners</p>
      </div>

      {/* Create form */}
      <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-3">
        <h3 className="text-sm font-semibold">Create New Banner</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted">Title *</label>
            <input
              value={form.title}
              onChange={e => setField('title', e.target.value)}
              placeholder="e.g. Deck Recommendations are here!"
              className="w-full mt-1 bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
              maxLength={100}
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">Subtitle (optional)</label>
            <input
              value={form.subtitle}
              onChange={e => setField('subtitle', e.target.value)}
              placeholder="Optional subtitle..."
              className="w-full mt-1 bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
              maxLength={200}
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">Link *</label>
            <input
              value={form.link}
              onChange={e => setField('link', e.target.value)}
              placeholder="/deck-rec"
              className="w-full mt-1 bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
              maxLength={200}
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">Badge Text</label>
            <input
              value={form.badge}
              onChange={e => setField('badge', e.target.value)}
              className="w-full mt-1 bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
              maxLength={20}
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">Color</label>
            <select
              value={form.color}
              onChange={e => setField('color', e.target.value)}
              className="w-full mt-1 bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
            >
              {COLORS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-text-muted">Duration</label>
            <select
              value={form.duration}
              onChange={e => setField('duration', Number(e.target.value))}
              className="w-full mt-1 bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
            >
              {DURATIONS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </div>
        </div>

        {/* Images */}
        <div>
          <label className="text-xs text-text-muted">
            Images{' '}
            <span className="opacity-50">(optional — auto-scrolls every 10s if multiple)</span>
          </label>
          <div className="flex gap-2 mt-1 flex-wrap items-center">
            <label className="px-3 py-1.5 text-xs bg-secondary text-black rounded cursor-pointer hover:opacity-90">
              {uploading ? 'Uploading...' : 'Upload Image'}
              <input
                ref={fileRef}
                type="file"
                accept=".jpg,.jpeg,.png,.webp,.gif"
                multiple
                className="hidden"
                onChange={e => uploadFiles(Array.from(e.target.files))}
              />
            </label>
            <input
              value={imageUrl}
              onChange={e => setImageUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addUrl()}
              placeholder="or paste URL..."
              className="flex-1 min-w-0 bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
            />
            <button
              onClick={addUrl}
              className="px-3 py-1.5 text-xs bg-bg-surface border border-border rounded hover:border-secondary"
            >
              Add URL
            </button>
          </div>
          {images.length > 0 && (
            <div className="mt-2 space-y-1">
              {images.map((url, i) => (
                <div key={i} className="flex items-center gap-2 bg-bg-surface rounded px-2 py-1">
                  <img
                    src={url}
                    className="w-10 h-6 object-cover rounded flex-shrink-0"
                    onError={e => { e.target.style.display = 'none' }}
                    alt=""
                  />
                  <span className="flex-1 text-xs text-text-muted truncate">{url}</span>
                  <button
                    onClick={() => removeImage(i)}
                    className="text-accent-red text-xs hover:opacity-80 flex-shrink-0"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={createBanner}
          disabled={creating}
          className="px-4 py-2 text-sm bg-accent-green text-white rounded hover:opacity-90 disabled:opacity-40"
        >
          {creating ? 'Creating...' : 'Create Banner'}
        </button>
      </div>

      {/* Banners list */}
      {banners.length === 0 ? (
        <p className="text-text-muted text-sm">No banners yet. Create one above.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ minWidth: 700 }}>
            <thead>
              <tr className="border-b border-border text-text-muted text-left">
                <th className="py-2 px-3">Title</th>
                <th className="py-2 px-3">Link</th>
                <th className="py-2 px-3">Color</th>
                <th className="py-2 px-3">Imgs</th>
                <th className="py-2 px-3 whitespace-nowrap">Expires</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {banners.map(b => {
                const expired = new Date(b.expires_at + 'Z') < now
                const statusEl = !b.active
                  ? <span className="text-accent-red">Inactive</span>
                  : expired
                  ? <span className="text-text-muted">Expired</span>
                  : <span className="text-accent-green">Live</span>

                return (
                  <tr key={b.id} className="border-b border-border/50 hover:bg-bg-surface/50">
                    <td className="py-2 px-3">
                      <div className="font-medium">{b.title}</div>
                      {b.subtitle && <div className="text-text-muted opacity-70">{b.subtitle}</div>}
                    </td>
                    <td className="py-2 px-3 text-secondary">{b.link}</td>
                    <td className="py-2 px-3">{b.color}</td>
                    <td className="py-2 px-3">{b.images?.length || '-'}</td>
                    <td className="py-2 px-3 whitespace-nowrap">{b.expires_at?.slice(0, 16).replace('T', ' ')}</td>
                    <td className="py-2 px-3">{statusEl}</td>
                    <td className="py-2 px-3">
                      <div className="flex gap-1">
                        <button
                          onClick={() => toggleBanner(b.id)}
                          className="px-2 py-0.5 bg-secondary/20 text-secondary rounded hover:bg-secondary/30"
                        >
                          {b.active ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          onClick={() => deleteBanner(b.id)}
                          className="px-2 py-0.5 bg-accent-red/20 text-accent-red rounded hover:bg-accent-red/30"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
