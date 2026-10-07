import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { applyForStorefront, getMyStorefrontApplications } from '@/api/store'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const inputCls =
  'w-full rounded-lg border border-border bg-bg-surface px-3 py-2.5 text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-colors'

const EMPTY = { name: '', contact_email: '', website: '', description: '', shipping: '' }

const STATUS_TEXT = {
  pending: 'Waiting for review',
  approved: 'Approved',
  declined: 'Not approved',
}

function Field({ id, label, hint, children }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-semibold mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-xs text-text-muted mt-1.5">{hint}</p>}
    </div>
  )
}

export default function StoreApply() {
  usePageTitle('Apply for a storefront')
  const [form, setForm] = useState(EMPTY)
  const [agreed, setAgreed] = useState(false)
  const [applications, setApplications] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(false)

  const load = () =>
    getMyStorefrontApplications()
      .then((d) => setApplications(d.applications || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  useEffect(() => { load() }, [])

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const pending = applications.find((a) => a.status === 'pending')

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await applyForStorefront({ ...form, agreed })
      setSent(true)
      setForm(EMPTY)
      setAgreed(false)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <Spinner className="py-20" />

  return (
    <div className="max-w-2xl mx-auto">
      <Link to="/store" className="text-sm text-text-muted hover:text-text transition-colors">
        &larr; Back to store
      </Link>
      <h1 className="text-2xl font-display text-secondary mt-3 mb-2">Apply to have a storefront</h1>
      <p className="text-text-muted mb-6">
        Run a playgroup, league or event series? Get your own tab in the Sorcery Community Store,
        and manage your products and orders from Store Admin.
      </p>

      {applications.length > 0 && (
        <div className="bg-bg-surface border border-border rounded-lg p-4 mb-6">
          <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wide mb-2">Your applications</h2>
          <ul className="space-y-1.5 text-sm">
            {applications.map((a) => (
              <li key={a.id} className="flex flex-wrap justify-between gap-2">
                <span className="font-medium">{a.name}</span>
                <span className={a.status === 'approved' ? 'text-accent-green' : 'text-text-muted'}>
                  {STATUS_TEXT[a.status] || a.status}
                  {a.status === 'approved' && a.storefront_slug && (
                    <>
                      {' · '}
                      <Link to={`/store?storefront=${a.storefront_slug}`} className="text-primary hover:underline">
                        View storefront
                      </Link>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sent && (
        <div className="bg-accent-green/10 border border-accent-green/30 rounded-lg px-4 py-3 mb-6 text-sm">
          Thanks! Your application is in. We'll message you on Discord once it's reviewed.
        </div>
      )}

      {pending ? (
        !sent && (
          <p className="text-sm text-text-muted">
            Your application for <span className="text-text font-medium">{pending.name}</span> is
            waiting for review. You can apply again once it's been looked at.
          </p>
        )
      ) : (
        <form onSubmit={submit} className="bg-bg-surface border border-border rounded-lg p-5 space-y-5">
          <Field id="sf-name" label="Storefront name">
            <input id="sf-name" className={inputCls} value={form.name} onChange={set('name')} maxLength={80} required />
          </Field>
          <Field id="sf-email" label="Contact email" hint="Buyers see this on their orders, for questions about them.">
            <input id="sf-email" type="email" className={inputCls} value={form.contact_email} onChange={set('contact_email')} required />
          </Field>
          <Field id="sf-site" label="Discord server or website (optional)">
            <input id="sf-site" className={inputCls} value={form.website} onChange={set('website')} placeholder="https://" />
          </Field>
          <Field id="sf-about" label="About your group, and what you'd sell">
            <textarea id="sf-about" rows={4} className={inputCls} value={form.description} onChange={set('description')} required />
          </Field>
          <Field id="sf-ship" label="Shipping" hint="Who packs and ships your orders, and where from.">
            <textarea id="sf-ship" rows={2} className={inputCls} value={form.shipping} onChange={set('shipping')} required />
          </Field>

          <fieldset className="border border-secondary/30 rounded-lg p-4">
            <legend className="px-1 text-sm font-semibold text-secondary">Storefront agreement</legend>
            <ul className="list-disc pl-5 text-sm text-text-muted space-y-1 mb-3">
              <li>We pack and ship our own orders and answer our buyers' questions.</li>
              <li>We only list products we're allowed to sell, and only use artwork we own or have permission to use. No official game art or logos without the publisher's permission.</li>
              <li>We keep our product details, stock and prices accurate.</li>
              <li>Sorcerers Summit can pause or remove our storefront at any time.</li>
            </ul>
            <label className="flex items-center gap-2.5 text-sm min-h-11 cursor-pointer">
              <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="w-4 h-4" />
              I agree to the storefront agreement
            </label>
          </fieldset>

          {error && <p className="text-accent-red text-sm">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !agreed}
            className="bg-primary hover:bg-primary-dark text-white font-semibold px-5 py-2.5 rounded-lg transition-colors disabled:opacity-50"
          >
            {submitting ? 'Sending…' : 'Send application'}
          </button>
        </form>
      )}
    </div>
  )
}
