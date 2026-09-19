import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'

// react-leaflet needs a real layout engine, so stub the pieces we render and
// assert on our own wrapper instead.
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => <div data-testid="leaflet">{children}</div>,
  TileLayer: () => null,
  CircleMarker: ({ children }) => <div data-testid="pin">{children}</div>,
  Popup: ({ children }) => <div>{children}</div>,
}))
vi.mock('leaflet/dist/leaflet.css', () => ({}))

import ApplicationsMap from '../ApplicationsMap'

const pinned = { id: 1, latitude: 37.6, longitude: -77.4, status: 'pending', city: 'Richmond' }
const unpinned = { id: 2, latitude: null, longitude: null, status: 'pending', city: 'Nowhere' }

describe('ApplicationsMap', () => {
  it('isolates the map so Leaflet z-indexes cannot paint over dialogs', () => {
    // Leaflet sets z-index 400-1000 on its panes and controls. Without a
    // stacking context here those escape and cover the application modal.
    const { container } = render(<ApplicationsMap applications={[]} />)
    expect(container.firstChild).toHaveClass('isolate')
  })

  it('plots only applications that have coordinates', () => {
    const { getAllByTestId, queryAllByTestId } = render(
      <ApplicationsMap applications={[pinned, unpinned]} />
    )
    expect(getAllByTestId('pin')).toHaveLength(1)
    expect(queryAllByTestId('leaflet')).toHaveLength(1)
  })

  it('renders without pins when nothing is geocoded', () => {
    const { queryAllByTestId } = render(<ApplicationsMap applications={[unpinned]} />)
    expect(queryAllByTestId('pin')).toHaveLength(0)
  })
})
