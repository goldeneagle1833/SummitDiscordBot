import usePageTitle from '@/hooks/usePageTitle'
import AdminCollapsible from '@/components/admin/AdminCollapsible'
import DashboardSection from '@/components/admin/DashboardSection'
import AnalyticsSection from '@/components/admin/AnalyticsSection'
import BannersSection from '@/components/admin/BannersSection'
import AdminActionsSection from '@/components/admin/AdminActionsSection'
import TransferHistorySection from '@/components/admin/TransferHistorySection'
import MatchNotesSection from '@/components/admin/MatchNotesSection'
import BlockedUsersSection from '@/components/admin/BlockedUsersSection'
import CardPointsSection from '@/components/admin/CardPointsSection'
import AuditLogTable from '@/components/admin/AuditLogTable'

export default function AuditLog() {
  usePageTitle('Admin Audit Log')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-display text-secondary">Admin Audit Log</h1>
        <p className="text-sm text-text-muted">History of all administrative actions</p>
      </div>
      <AdminCollapsible title="Dashboard" subtitle="Community health at a glance" defaultOpen>
        <DashboardSection />
      </AdminCollapsible>
      <AdminCollapsible title="Site Analytics" subtitle="Page views and banner clicks">
        <AnalyticsSection />
      </AdminCollapsible>
      <AdminCollapsible title="Matches with Notes" subtitle="All matches where players left a comment">
        <MatchNotesSection />
      </AdminCollapsible>
      <AdminCollapsible title="Promo Banners" subtitle="Manage home page promotional banners">
        <BannersSection />
      </AdminCollapsible>
      <AdminCollapsible title="Transfer Account History" subtitle="Move all match history, ELO, and data from one account to another">
        <TransferHistorySection />
      </AdminCollapsible>
      <AdminCollapsible title="Card Points" subtitle="Assign point values to cards for deck budget restrictions">
        <CardPointsSection />
      </AdminCollapsible>
      <AdminCollapsible title="Admin Actions" subtitle="Perform administrative operations">
        <AdminActionsSection />
      </AdminCollapsible>
      <AdminCollapsible title="Blocked Users" subtitle="All block records across players">
        <BlockedUsersSection />
      </AdminCollapsible>
      <AdminCollapsible title="Audit Log" subtitle="History of administrative actions">
        <AuditLogTable />
      </AdminCollapsible>
    </div>
  )
}
