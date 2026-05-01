export default function StatCard({ label, value }) {
  return (
    <div className="bg-bg-surface border border-border rounded-lg p-3 text-center">
      <div className="text-lg font-bold text-text-primary">{value}</div>
      <div className="text-xs text-text-muted">{label}</div>
    </div>
  )
}
