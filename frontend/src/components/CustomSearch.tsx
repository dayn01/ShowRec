import { useState } from "react";
import { api } from "../api";
import AiPickCard from "./AiPickCard";
import DetailModal from "./DetailModal";

const ALL_GENRES = [
  "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
  "Drama", "Fantasy", "Horror", "Mystery", "Romance", "Sci-Fi",
  "Thriller", "Western", "Family", "History", "Music", "War",
];

export default function CustomSearch() {
  const [mediaType, setMediaType] = useState<"any" | "tv" | "movie">("any");
  const [selectedGenres, setSelectedGenres] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ id: number; mediaType: string } | null>(null);

  function toggleGenre(g: string) {
    setSelectedGenres(prev =>
      prev.includes(g) ? prev.filter(x => x !== g) : [...prev, g]
    );
  }

  async function search() {
    if (!prompt && selectedGenres.length === 0 && mediaType === "any") return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.getCustomRecommendations({
        media_type: mediaType,
        genres: selectedGenres,
        prompt,
      });
      setResult(data);
    } catch (e: any) {
      setError("Could not generate recommendations — check the backend is running.");
    } finally {
      setLoading(false);
    }
  }

  const btn = (label: string, value: typeof mediaType) => (
    <button
      key={value}
      onClick={() => setMediaType(value)}
      style={{
        padding: "7px 18px", borderRadius: 20, border: "1px solid var(--border)",
        background: mediaType === value ? "var(--accent)" : "var(--surface)",
        color: mediaType === value ? "#fff" : "var(--muted)",
        fontWeight: mediaType === value ? 600 : 400,
        cursor: "pointer", fontSize: 13, transition: "all 0.15s",
      }}
    >{label}</button>
  );

  return (
    <div>
      {/* Form */}
      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 14, padding: 24, marginBottom: 24,
        display: "flex", flexDirection: "column", gap: 20,
      }}>
        {/* Media type */}
        <div>
          <label style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, display: "block", marginBottom: 8 }}>
            Type
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            {btn("Any", "any")}
            {btn("TV Shows", "tv")}
            {btn("Films", "movie")}
          </div>
        </div>

        {/* Genres */}
        <div>
          <label style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, display: "block", marginBottom: 8 }}>
            Genres <span style={{ fontWeight: 400, textTransform: "none" }}>(optional)</span>
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {ALL_GENRES.map(g => (
              <button
                key={g}
                onClick={() => toggleGenre(g)}
                style={{
                  padding: "5px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
                  border: selectedGenres.includes(g) ? "1px solid var(--accent)" : "1px solid var(--border)",
                  background: selectedGenres.includes(g) ? "rgba(124,106,247,0.2)" : "var(--surface2)",
                  color: selectedGenres.includes(g) ? "var(--accent2)" : "var(--muted)",
                  fontWeight: selectedGenres.includes(g) ? 600 : 400,
                  transition: "all 0.15s",
                }}
              >{g}</button>
            ))}
          </div>
        </div>

        {/* Free text */}
        <div>
          <label style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, display: "block", marginBottom: 8 }}>
            Describe what you want <span style={{ fontWeight: 400, textTransform: "none" }}>(optional)</span>
          </label>
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder={`e.g. "a TV show like Severance but funnier" or "something with a twist ending like Gone Girl"`}
            rows={3}
            style={{
              width: "100%", background: "var(--surface2)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "12px 14px", color: "var(--text)", fontSize: 14,
              resize: "vertical", fontFamily: "inherit", outline: "none",
              transition: "border-color 0.15s",
            }}
            onFocus={e => { e.target.style.borderColor = "var(--accent)"; }}
            onBlur={e => { e.target.style.borderColor = "var(--border)"; }}
            onKeyDown={e => { if (e.key === "Enter" && e.ctrlKey) search(); }}
          />
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>Ctrl+Enter to search</div>
        </div>

        <button
          onClick={search}
          disabled={loading || (!prompt && selectedGenres.length === 0 && mediaType === "any")}
          style={{
            padding: "10px 28px", borderRadius: 20, border: "none",
            background: "var(--accent)", color: "#fff", fontWeight: 700,
            fontSize: 14, cursor: "pointer", alignSelf: "flex-start",
            opacity: loading || (!prompt && selectedGenres.length === 0 && mediaType === "any") ? 0.5 : 1,
            transition: "opacity 0.15s",
          }}
        >
          {loading ? "Searching…" : "✨ Generate Recommendations"}
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: "center", padding: 48 }}>
          <div style={{ fontSize: 28, marginBottom: 10 }}>✨</div>
          <div style={{ color: "var(--muted)", fontSize: 14 }}>
            Claude is finding the best matches…
            <br /><span style={{ fontSize: 12 }}>Usually takes 10–15 seconds</span>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ color: "var(--red)", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, fontSize: 14 }}>
          {error}
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div>
          {result.query_summary && (
            <div style={{
              background: "var(--surface)", border: "1px solid var(--border)",
              borderRadius: 12, padding: "12px 18px", marginBottom: 20,
              borderLeft: "3px solid var(--accent)", fontSize: 14, color: "var(--muted)",
            }}>
              <span style={{ color: "var(--accent2)", fontWeight: 600 }}>✨ </span>
              {result.query_summary}
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {result.picks.map((item: any) => (
              <AiPickCard
                key={item.id}
                item={item}
                onClick={() => setSelected({ id: item.id, mediaType: item.media_type })}
              />
            ))}
          </div>
        </div>
      )}

      {selected && (
        <DetailModal
          tmdbId={selected.id}
          mediaType={selected.mediaType}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
