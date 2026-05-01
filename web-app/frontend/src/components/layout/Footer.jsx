import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer className="bg-bg-surface border-t border-border mt-auto">
      <div className="max-w-content mx-auto px-4 py-8">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-sm">
          <div>
            <h3 className="font-display text-secondary mb-3">Sorcerers Summit</h3>
            <p className="text-text-muted">
              Community hub for Sorcery: Contested Realm
            </p>
          </div>
          <div>
            <h4 className="font-semibold text-text mb-2">Links</h4>
            <div className="flex flex-col gap-1">
              <Link to="/about" className="text-text-muted hover:text-text transition-colors">About</Link>
              <Link to="/help" className="text-text-muted hover:text-text transition-colors">Help</Link>
              <Link to="/community" className="text-text-muted hover:text-text transition-colors">Community</Link>
            </div>
          </div>
          <div>
            <h4 className="font-semibold text-text mb-2">Legal</h4>
            <div className="flex flex-col gap-1">
              <Link to="/privacy" className="text-text-muted hover:text-text transition-colors">Privacy Policy</Link>
              <Link to="/terms" className="text-text-muted hover:text-text transition-colors">Terms of Service</Link>
            </div>
          </div>
        </div>
        <div className="mt-6 pt-4 border-t border-border text-center text-xs text-text-muted">
          &copy; {new Date().getFullYear()} Sorcerers Summit
        </div>
      </div>
    </footer>
  )
}
