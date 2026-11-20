// Small "NEW" pill for items added since the person last opened the page
export default function NewTag({ className = '' }) {
  return (
    <span className={`inline-block text-[10px] font-bold uppercase tracking-wide bg-white text-black px-1.5 py-0.5 rounded shrink-0 ${className}`}>
      New
    </span>
  )
}
