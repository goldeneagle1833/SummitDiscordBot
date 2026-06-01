import usePageTitle from '@/hooks/usePageTitle'
import DashboardSection from '@/components/admin/DashboardSection'
import AnalyticsSection from '@/components/admin/AnalyticsSection'
import BannersSection from '@/components/admin/BannersSection'
import AdminActionsSection from '@/components/admin/AdminActionsSection'
import TransferHistorySection from '@/components/admin/TransferHistorySection'
import AuditLogTable from '@/components/admin/AuditLogTable'

export default function AuditLog() {
  usePageTitle('Admin Audit Log')

  return (
    <div className="space-y-12">
      <div>
        <h1 className="text-2xl font-display text-secondary">Admin Audit Log</h1>
        <p className="text-sm text-text-muted">History of all administrative actions</p>
      </div>
      <DashboardSection />
      <AnalyticsSection />
      <BannersSection />
      <TransferHistorySection />
      <AdminActionsSection />
      <AuditLogTable />
    </div>
  )
}
