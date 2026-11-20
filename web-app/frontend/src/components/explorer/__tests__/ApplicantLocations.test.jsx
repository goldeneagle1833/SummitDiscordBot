import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// Leaflet needs real layout; jsdom has none.
vi.mock('../ApplicationsMap', () => ({
  default: ({ applications, onSelect }) => (
    <div data-testid="map">
      {applications.map((a) => (
        <button key={a.id} onClick={() => onSelect(a)}>pin {a.id}</button>
      ))}
    </div>
  ),
}))

import ApplicantLocations, { regionOf } from '../ApplicantLocations'

const apps = [
  { id: 1, state: 'oh', country: 'USA', latitude: 40, longitude: -83, status: 'pending' },
  { id: 2, state: 'OH', country: 'United States', latitude: 41, longitude: -81, status: 'approved' },
  { id: 3, state: 'TX', country: '', latitude: 30, longitude: -97, status: 'pending' },
  { id: 4, state: 'Ontario', country: 'Canada', latitude: null, longitude: null, status: 'pending' },
  { id: 5, state: 'CA', country: 'USA', latitude: 34, longitude: -118, source: 'admin_added' },
]

describe('regionOf', () => {
  it('uses the state for US applicants and the country otherwise', () => {
    expect(regionOf(apps[0])).toBe('OH')
    expect(regionOf(apps[2])).toBe('TX')
    expect(regionOf(apps[3])).toBe('Canada')
  })
})

describe('ApplicantLocations', () => {
  beforeEach(() => localStorage.clear())

  it('maps submitted applications with coordinates and counts regions', async () => {
    render(<ApplicantLocations applications={apps} />)
    expect(await screen.findByTestId('map')).toBeInTheDocument()
    // Candidate #5 is left out; #4 has no pin.
    expect(screen.getAllByRole('button', { name: /^pin/ })).toHaveLength(3)
    expect(screen.queryByText('pin 5')).not.toBeInTheDocument()
    expect(screen.getByText(/4 applications from 3 regions/)).toBeInTheDocument()
    expect(screen.getByText(/1 without a pin yet/)).toBeInTheDocument()
    expect(screen.getByText('OH').textContent).toContain('2')
  })

  it('opens an application when its pin is clicked', async () => {
    const onSelect = vi.fn()
    render(<ApplicantLocations applications={apps} onSelect={onSelect} />)
    fireEvent.click(await screen.findByText('pin 2'))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))
  })

  it('collapses and remembers it', async () => {
    const { unmount } = render(<ApplicantLocations applications={apps} />)
    await screen.findByTestId('map')
    fireEvent.click(screen.getByRole('button', { name: /Applicant locations/ }))
    expect(screen.queryByTestId('map')).not.toBeInTheDocument()
    unmount()
    render(<ApplicantLocations applications={apps} />)
    expect(screen.queryByTestId('map')).not.toBeInTheDocument()
  })

  it('renders nothing with no submitted applications', () => {
    const { container } = render(<ApplicantLocations applications={[apps[4]]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
