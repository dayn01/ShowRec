import { Recommendation } from "../api";

export interface SortOption {
  id: string;
  label: string;
}

/** Compact "Sort: [select]" control, styled to match the app's surfaces. */
export function SortControl({ options, value, onChange }: {
  options: SortOption[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--muted)" }}>
      Sort
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          background: "var(--surface2)", border: "1px solid var(--border)",
          borderRadius: 8, color: "var(--text)", fontSize: 13,
          padding: "6px 10px", cursor: "pointer", outline: "none",
        }}
      >
        {options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
      </select>
    </label>
  );
}

const titleOf = (r: Recommendation) => (r.title || r.name || "").toLowerCase();
const yearOf = (r: Recommendation) => {
  const d = r.release_date || r.first_air_date || "";
  return d ? parseInt(d.slice(0, 4)) || 0 : 0;
};

/**
 * Comparator for the generic, page-agnostic sort ids (title / rating / release).
 * Returns null for any other id (e.g. "relevance", "recent", "smart") so the
 * page keeps its own default ordering.
 */
export function recComparator(id: string): ((a: Recommendation, b: Recommendation) => number) | null {
  switch (id) {
    case "title":   return (a, b) => titleOf(a).localeCompare(titleOf(b));
    case "rating":  return (a, b) => (b.vote_average || 0) - (a.vote_average || 0);
    case "release": return (a, b) => yearOf(b) - yearOf(a);
    default:        return null;
  }
}

/** Apply a generic sort id to a list, leaving it untouched for page-specific ids. */
export function sortRecommendations(items: Recommendation[], id: string): Recommendation[] {
  const cmp = recComparator(id);
  return cmp ? [...items].sort(cmp) : items;
}
