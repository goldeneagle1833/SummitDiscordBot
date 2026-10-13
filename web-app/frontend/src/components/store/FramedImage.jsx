// A product image cropped to fill its box, positioned and zoomed by the
// framing saved in Store Admin ({ x, y, zoom }; x/y are percents).
export const DEFAULT_FRAMING = { x: 50, y: 50, zoom: 1 }

export function framingStyle(framing) {
  const { x, y, zoom } = { ...DEFAULT_FRAMING, ...framing }
  return {
    objectPosition: `${x}% ${y}%`,
    transformOrigin: `${x}% ${y}%`,
    transform: zoom !== 1 ? `scale(${zoom})` : undefined,
  }
}

export default function FramedImage({ src, alt, framing, className = '', imgRef, onLoad }) {
  return (
    <div className={`overflow-hidden ${className}`}>
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        onLoad={onLoad}
        draggable={false}
        className="w-full h-full object-cover select-none"
        style={framingStyle(framing)}
      />
    </div>
  )
}
