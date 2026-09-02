// `page` is clamped by the caller (paginate() below) before being passed
// in, so it's always valid for the current item count -- this just
// renders Prev/Next around it. Always renders, Prev/Next disabled on a
// single page, so columns with few items (e.g. Dashboard's Scheduled/
// Ongoing) still show the same pagination bar as one with enough to
// actually page through, instead of the layout shifting depending on
// how much data happens to be in each column right now.
export default function Pagination({ page, totalPages, onChange }) {
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
