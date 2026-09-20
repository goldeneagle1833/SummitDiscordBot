import SeriesMap from './SeriesMap'

// Bigger events get a bigger dot, so the map reads as "where the Series is
// busy" at a glance rather than just "where it exists".
function radiusFor(players) {
  if (!players) return 6
  if (players >= 48) return 13
  if (players >= 32) return 11
  if (players >= 16) return 9
  return 7
}

const EVENT_COLOR = '#f5c451'

export default function EventsMap({ events }) {
  const points = events
    .filter((e) => typeof e.latitude === 'number' && typeof e.longitude === 'number')
    .map((event) => ({
      id: event.id,
      latitude: event.latitude,
      longitude: event.longitude,
      color: EVENT_COLOR,
      radius: radiusFor(event.total_players),
      title: event.event_name,
      lines: [
        event.venue_name,
        event.event_date,
        event.total_players ? `${event.total_players} players` : null,
      ],
    }))

  return <SeriesMap points={points} height="h-96" storageKey="explorer-events-map-style" />
}
