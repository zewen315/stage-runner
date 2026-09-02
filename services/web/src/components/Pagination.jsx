// `page` is clamped by the caller (paginate() below) before being passed
// in, so it's always valid for the current item count -- this just
// renders Prev/Next around it. Renders nothing for a single page, so
// callers can use it unconditionally.
export default function Pagination({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null
  return (
    <div className="pagination">
      <button className="btn-ghost" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        &larr; Prev
      </button>
      <span className="pagination-status">
        Page {page} of {totalPages}
      </span>
      <button className="btn-ghost" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        Next &rarr;
      </button>
    </div>
  )
}

// Slices `items` into `pageSize`-sized pages, clamping the requested page
// into range (so a list that shrank on refresh, e.g. a run finishing and
// leaving the "Ongoing" bucket, never renders a blank page).
export function paginate(items, page, pageSize) {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize))
  const current = Math.min(Math.max(1, page), totalPages)
  return { items: items.slice((current - 1) * pageSize, current * pageSize), page: current, totalPages }
}
