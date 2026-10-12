import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { confirmMetaReportEmail, unsubscribeMetaReportEmail } from '@/api/metaReports'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

/** Landing page for the confirm and unsubscribe links in Meta Report emails. */
export default function MetaReportEmail() {
  usePageTitle('Meta Report emails')
  const [params] = useSearchParams()
  const confirm = params.get('confirm')
  const unsubscribe = params.get('unsubscribe')
  const [state, setState] = useState({ status: 'busy', message: '' })
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true
    const token = confirm || unsubscribe
    if (!token) {
      setState({ status: 'error', message: 'This link is missing its code. Use the link from your email.' })
      return
    }
    const call = confirm ? confirmMetaReportEmail : unsubscribeMetaReportEmail
    call(token)
      .then(() => setState({
        status: 'done',
        message: confirm
          ? "You're signed up. The next Meta Report will land in your inbox."
          : "You're unsubscribed. You won't get any more Meta Report emails.",
      }))
      .catch((err) => setState({ status: 'error', message: err.message || 'Something went wrong. Try again.' }))
  }, [confirm, unsubscribe])

  return (
    <div className="max-w-xl mx-auto py-10">
      <h1 className="font-display text-secondary text-3xl mb-4">Meta Report emails</h1>
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        {state.status === 'busy' ? <Spinner className="py-6" /> : (
          <p className={state.status === 'error' ? 'text-accent-red' : ''} role="status">{state.message}</p>
        )}
      </div>
      <p className="mt-4 text-sm">
        <Link to="/meta-report" className="text-primary hover:underline">Read the latest Meta Report</Link>
      </p>
    </div>
  )
}
