import { describe, it, expect } from 'vitest'
import { splitDescription } from '../apparelDetails'

const PORT_AND_CO = `<ul>
<li>4.5-ounce, 60/40 ring spun cotton/poly</li>
<li>1x1 rib knit neck</li>
<li>Shoulder-to-shoulder taping</li>
<li><h4>PRODUCT MEASUREMENTS</h4>
<table><tr><th></th><th>S</th><th>M</th></tr><tr><td>Chest Width</td><td>19</td><td>20 1/2</td></tr></table>
<p><strong>BODY LENGTH AT BACK</strong></p><p>Measured from high point shoulder to finished hem at the back.</p>
</li>
</ul>`

describe('splitDescription', () => {
  it('puts the fabric bullets in details and the measurements in the size chart', () => {
    const { details, sizeChart } = splitDescription(PORT_AND_CO)
    expect(details).toContain('ring spun cotton/poly')
    expect(details).toContain('Shoulder-to-shoulder taping')
    expect(details).not.toContain('Chest Width')
    expect(details).not.toContain('MEASUREMENTS')
    expect(sizeChart).toContain('<table')
    expect(sizeChart).toContain('Chest Width')
    expect(sizeChart).toContain('Measured from high point shoulder')
    expect(sizeChart).not.toContain('PRODUCT MEASUREMENTS')
  })

  it('keeps a description with no size chart whole', () => {
    const { details, sizeChart } = splitDescription('<p><strong>Product Description</strong></p><p>Cozy sweats.</p><ul><li>7.8-ounce fleece</li></ul>')
    expect(details).toContain('Cozy sweats.')
    expect(details).toContain('7.8-ounce fleece')
    expect(sizeChart).toBe('')
  })

  it('starts the size chart at a table when there is no heading', () => {
    const { details, sizeChart } = splitDescription('<p>Soft tee</p><table><tr><td>Chest</td><td>19</td></tr></table>')
    expect(details).toContain('Soft tee')
    expect(sizeChart).toContain('Chest')
  })

  it('drops scripts, attributes, images and links', () => {
    const { details } = splitDescription('<p onclick="x()" style="color:red">Hi <a href="javascript:alert(1)">there</a></p><script>alert(1)</script><img src=x onerror="alert(1)">')
    expect(details).toBe('<p>Hi there</p>')
  })

  it('handles an empty description', () => {
    expect(splitDescription('')).toEqual({ details: '', sizeChart: '' })
  })
})
