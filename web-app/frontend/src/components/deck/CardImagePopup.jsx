export default function CardImagePopup({ imageFile, anchorRect }) {
  if (!imageFile || !anchorRect) return null
  const popupW = 220
  const spaceRight = window.innerWidth - anchorRect.right
  const left = spaceRight >= popupW + 12 ? anchorRect.right + 8 : anchorRect.left - popupW - 8
  const maxTop = window.innerHeight - 320
  const top = Math.min(anchorRect.top, Math.max(0, maxTop))

  return (
    <div
      className="fixed z-50 pointer-events-none"
      style={{ left: Math.max(4, left), top }}
    >
      <img
        src={`/card-images/${imageFile}`}
        alt="Card"
        style={{ width: popupW }}
        className="rounded shadow-lg"
      />
    </div>
  )
}
