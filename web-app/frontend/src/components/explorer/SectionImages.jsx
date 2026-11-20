/**
 * Pictures under (or beside) an Explorer Series site section. One picture
 * sits next to the text on wide screens; several make a gallery that scrolls
 * sideways on a phone. Tapping one opens it full size.
 */
export function SectionGallery({ images }) {
  if (!images?.length) return null
  return (
    <div className="mt-4 flex sm:grid sm:grid-cols-3 gap-3 overflow-x-auto sm:overflow-visible snap-x snap-mandatory pb-1 -mx-1 px-1">
      {images.map((src) => (
        <a
          key={src}
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 w-[78%] sm:w-auto snap-start rounded-lg overflow-hidden border border-[color:var(--es-rule)] bg-[color:var(--es-card-2)]"
        >
          <img src={src} alt="" loading="lazy" className="w-full aspect-[4/3] object-cover" />
        </a>
      ))}
    </div>
  )
}

export function SectionPicture({ src }) {
  return (
    <a href={src} target="_blank" rel="noopener noreferrer" className="block rounded-lg overflow-hidden border border-[color:var(--es-rule)] bg-[color:var(--es-card-2)]">
      <img src={src} alt="" loading="lazy" className="w-full h-auto object-cover" />
    </a>
  )
}
