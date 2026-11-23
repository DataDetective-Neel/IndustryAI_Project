import React from "react";

export default function Pagination({ page, pageCount, onChange }) {
  if (pageCount <= 1) return null;
  return <nav className="pagination" aria-label="Pagination">
    <button onClick={() => onChange(page - 1)} disabled={page <= 1}>Previous</button>
    <span>Page {page} of {pageCount}</span>
    <button onClick={() => onChange(page + 1)} disabled={page >= pageCount}>Next</button>
  </nav>;
}

export function usePage(items, pageSize = 10) {
  const [page, setPage] = React.useState(1);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  React.useEffect(() => setPage(value => Math.min(value, pageCount)), [pageCount]);
  return { page, setPage, pageCount, rows: items.slice((page - 1) * pageSize, page * pageSize) };
}
