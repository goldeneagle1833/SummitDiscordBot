import SeriesMap from './SeriesMap'

export const STATUS_COLORS = {
  pending: '#fbbf24',
  pre_approved: '#60a5fa',
  approved: '#34d399',
  rejected: '#f87171',
}

/**
 * Pin map of Explorer applications, coloured by review status. Applications
 * without coordinates are not plotted — the review board counts them
 * separately so an admin can retry geocoding.
 */
export default function ApplicationsMap({ applications, onSelect }) {
  const points = applications
    .filter((a) => typeof a.latitude === 'number' && typeof a.longitude === 'number')
    .map((application) => ({
      id: application.id,
      latitude: application.latitude,
      longitude: application.longitude,
      color: STATUS_COLORS[application.status] || STATUS_COLORS.pending,
      title: [application.first_name, application.last_name].filter(Boolean).join(' ')
        || application.discord_handle
        || 'Application',
      lines: [
        application.lgs_name,
        [application.city, application.state].filter(Boolean).join(', '),
        application.average_score != null ? `Avg score: ${application.average_score}` : null,
      ],
      application,
    }))

  return (
    <SeriesMap
      points={points}
      storageKey="explorer-applications-map-style"
      onSelect={(point) => onSelect?.(point.application)}
    />
  )
}
