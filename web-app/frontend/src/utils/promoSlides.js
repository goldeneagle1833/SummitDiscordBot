// The home page promo carousel: where each slide comes from, and the order /
// on-off settings admins save in Admin > Home Promos.
import { get } from '@/api/client'
import { articleImage, articlePath, listArticles } from '@/api/articles'

export const NEW_ARTICLE_DAYS = 14

// Slides that fill themselves in from site data. Each has one fixed slot, so
// its place and on/off setting carry over when the content inside changes
// (a new Player of the Day, a newer article). Banners each get "promo-<id>".
export const BUILT_IN_SLOTS = [
  { slot: 'kudos', label: 'Player of the Day', source: 'Picked daily from player kudos' },
  { slot: 'new-event', label: 'Newest Top 8 event', source: 'Latest event with decklists' },
  { slot: 'new-article', label: 'Newest player article', source: `Shows for ${NEW_ARTICLE_DAYS} days after an article is published` },
  { slot: 'spotlight', label: 'Daily spotlight', source: 'Rotating player or deck spotlight' },
  { slot: 'event-spotlight', label: 'Event spotlight', source: 'Upcoming or recent event' },
  { slot: 'staff-pick', label: 'Staff pick deck', source: 'From Deck Recommendations' },
]

const isYouTubeLink = (url) => url && /youtu\.?be/i.test(url)

export function articleSlide(article) {
  if (!article) return null
  return {
    key: `article-${article.id}`, slot: 'new-article', badge: 'NEW ARTICLE', color: 'blue',
    title: article.title,
    subtitle: article.summary,
    extra: `By ${article.author_name}${article.external_site ? ` on ${article.external_site}` : ''}`,
    link: articlePath(article),
    thumbnail: articleImage(article),
    analyticsType: 'new_article',
    cta: 'Read article',
  }
}

export function bannerSlide(b) {
  return {
    key: `promo-${b.id}`, slot: `promo-${b.id}`, badge: isYouTubeLink(b.link) ? 'VIDEO' : b.badge_text, color: b.color,
    title: b.title, subtitle: b.subtitle, link: b.link,
    thumbnail: b.images?.[0] || null, analyticsType: `promo_${b.id}`,
  }
}

/**
 * Fetch every slide source. Returns { slides, layout }: slides in the
 * built-in default order with nothing filtered out, and the saved layout.
 */
export async function loadPromoSlides() {
  const [bannerData, spotlight, eventSpotlight, newEvent, staffPick, kudosSpotlight, newArticle] = await Promise.all([
    get('/api/analytics/banners/active').then(d => (d.success ? d : {})).catch(() => ({})),
    get('/api/spotlight').then(d => (d.success && d.spotlight ? d.spotlight : null)).catch(() => null),
    get('/api/event-spotlight').then(d => (d.success && d.event_spotlight ? d.event_spotlight : null)).catch(() => null),
    get('/api/recent-event').then(d => d?.event || null).catch(() => null),
    get('/api/deck-rec/staff-pick').then(d => (d.success && d.staff_pick ? d.staff_pick : null)).catch(() => null),
    get('/api/kudos-spotlight').then(d => (d.success && d.kudos_spotlight ? d.kudos_spotlight : null)).catch(() => null),
    listArticles({ days: NEW_ARTICLE_DAYS }).then(d => d.articles?.[0] || null).catch(() => null),
  ])
  const banners = bannerData?.banners || []
  const slides = []

  // Player of the Day from kudos (positive player reports) leads by default.
  if (kudosSpotlight) {
    slides.push({
      key: 'kudos-spotlight', slot: 'kudos', badge: kudosSpotlight.badge_text, color: kudosSpotlight.color,
      title: kudosSpotlight.title, subtitle: kudosSpotlight.subtitle, link: kudosSpotlight.link,
      thumbnail: kudosSpotlight.image_url || null, analyticsType: 'spotlight_kudos_player_of_the_day',
      extra: `👏 ${kudosSpotlight.kudos?.credit || 'Kudos from an opponent'}`,
      cta: 'View profile',
    })
  }

  if (newEvent) {
    slides.push({
      key: 'new-event', slot: 'new-event', badge: 'NEW', color: 'blue',
      title: newEvent.name, subtitle: 'New Top 8 decklists added',
      link: `/top-8/${newEvent.folder}`, thumbnail: null, analyticsType: 'new_event',
    })
  }

  const articleItem = articleSlide(newArticle)
  if (articleItem) slides.push(articleItem)

  for (const b of banners) slides.push(bannerSlide(b))

  if (spotlight) {
    slides.push({
      key: 'spotlight', slot: 'spotlight', badge: spotlight.badge_text, color: spotlight.color,
      title: spotlight.title, subtitle: spotlight.subtitle, link: spotlight.link,
      thumbnail: spotlight.image_url || spotlight.stats?.avatar_bg_image || null,
      analyticsType: `spotlight_${spotlight.type}`,
    })
  }

  if (eventSpotlight) {
    slides.push({
      key: 'event-spotlight', slot: 'event-spotlight', badge: eventSpotlight.badge_text, color: eventSpotlight.color,
      title: eventSpotlight.title, subtitle: eventSpotlight.subtitle, link: eventSpotlight.link,
      thumbnail: eventSpotlight.image_url || null, analyticsType: 'event_spotlight',
    })
  }

  if (staffPick) {
    slides.push({
      key: 'staff-pick', slot: 'staff-pick', badge: staffPick.is_new ? 'NEW STAFF PICK' : 'STAFF PICK', color: 'gold',
      title: staffPick.deck_name, subtitle: staffPick.primer || `${staffPick.avatar_name} deck`,
      link: `/deck-rec/${staffPick.deck_id}`,
      thumbnail: staffPick.avatar_image || null, analyticsType: 'staff_pick',
    })
  }

  return { slides, layout: bannerData?.layout || null }
}

/**
 * Put items in the saved order. Items carry a `slot`. Slots never saved (a
 * banner shared after the last save) keep their default spot: right after
 * the item that comes before them in the default order.
 */
export function orderBySlots(items, order) {
  if (!order?.length) return [...items]
  const pos = new Map(order.map((s, i) => [s, i]))
  const result = items.filter(it => pos.has(it.slot)).sort((a, b) => pos.get(a.slot) - pos.get(b.slot))
  let prev = null
  for (const it of items) {
    if (pos.has(it.slot)) { prev = it; continue }
    const at = prev ? result.indexOf(prev) + 1 : 0
    result.splice(at, 0, it)
    prev = it
  }
  return result
}

/** The carousel as visitors see it: hidden slots removed, saved order applied. */
export function applyPromoLayout(slides, layout) {
  if (!layout) return slides
  const hidden = new Set(layout.hidden || [])
  return orderBySlots(slides.filter(s => !hidden.has(s.slot)), layout.order)
}
