import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, UpcomingEpisode } from "../api";
import DetailModal from "../components/DetailModal";

function groupByDate(episodes: UpcomingEpisode[]): Record<string, UpcomingEpisode[]> {
  const groups: Record<string, UpcomingEpisode[]> = {};
  for (const ep of episodes) {
    const date = ep.first_aired?.slice(0, 10) ?? "Unknown";
    if (!groups[date]) groups[date] = [];
    groups[date].push(ep);
  }
  return groups;
}

function formatDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  const label =
    diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : diff === -1 ? "Yesterday" : null;
  const full = d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
  return label ? `${label} — ${full}` : full;
}

export default function Upcoming() {
  const [days, setDays] = useState(30);
  const [selected, setSelected] = useState<number | null>(null);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["upcoming", days],
    queryFn: () => api.getUpcoming(days),
  });

  const notify = useMutation({ mutationFn: api.triggerNotification });

  const grouped = groupByDate(data?.episodes ?? []);
  const dates = Object.keys(grouped).sort();
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 8 }}>
          {[7, 14, 30, 60].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              style={{
                padding: "6px 14px", borderRadius: 20,
                border: "1px solid var(--border)",
                background: days === d ? "var(--accent)" : "var(--surface)",
                color: days === d ? "#fff" : "var(--muted)",
                cursor: "pointer", fontSize: 13,
              }}
            >
              {d}d
            </button>
          ))}
        </div>

        <button
          onClick={() => notify.mutate()}
          disabled={notify.isPending}
          style={{
            marginLeft: "auto", padding: "7px 16px", borderRadius: 20,
            border: "1px solid var(--border)", background: "var(--surface2)",
            color: "var(--text)", cursor: "pointer", fontSize: 13,
          }}
        >
          {notify.isPending ? "Sending…" : notify.isSuccess ? "Sent ✓" : "Send HA Notification"}
        </button>
      </div>

      {isLoading && (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 60 }}>Loading…</div>
      )}

      {isError && (
        <div style={{ color: "var(--red)", padding: 24 }}>
          Failed to load — check your Trakt token in .env
        </div>
      )}

      {dates.length === 0 && !isLoading && !isError && (
        <div style={{ color: "var(--muted)", textAlign: "center", padding: 60 }}>
          No upcoming episodes in the next {days} days.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {dates.map(date => (
          <div key={date}>
            <div style={{
              fontSize: 13, fontWeight: 600, color: "var(--accent2)",
              marginBottom: 10, paddingBottom: 6,
              borderBottom: "1px solid var(--border)",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              {formatDate(date)}
              {date === today && (
                <span style={{
                  background: "var(--accent)", borderRadius: 10,
                  padding: "1px 8px", fontSize: 11, color: "#fff",
                }}>TODAY</span>
              )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {grouped[date].map((ep, i) => {
                const tmdbId = ep.show.ids?.tmdb;
                return (
                <div key={i}
                  onClick={() => tmdbId && setSelected(tmdbId)}
                  title={tmdbId ? "View details" : undefined}
                  style={{
                    background: "var(--surface)", border: "1px solid var(--border)",
                    borderRadius: 10, padding: "12px 16px",
                    display: "flex", gap: 16, alignItems: "flex-start",
                    cursor: tmdbId ? "pointer" : "default",
                    transition: "border-color 0.15s, transform 0.15s",
                  }}
                  onMouseEnter={e => { if (tmdbId) (e.currentTarget as HTMLElement).style.borderColor = "var(--accent)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = "var(--border)"; }}
                >
                  <div style={{
                    minWidth: 48, textAlign: "center",
                    background: "var(--surface2)", borderRadius: 8,
                    padding: "6px 4px",
                  }}>
                    <div style={{ fontSize: 11, color: "var(--muted)" }}>S{String(ep.episode.season).padStart(2, "0")}</div>
                    <div style={{ fontSize: 16, fontWeight: 700 }}>E{String(ep.episode.number).padStart(2, "0")}</div>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{ep.show.title}</div>
                    <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 2 }}>
                      {ep.episode.title}
                    </div>
                    {ep.episode.overview && (
                      <div style={{
                        fontSize: 12, color: "var(--muted)", marginTop: 4,
                        display: "-webkit-box", WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical", overflow: "hidden",
                      }}>
                        {ep.episode.overview}
                      </div>
                    )}
                  </div>
                </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <DetailModal tmdbId={selected} mediaType="tv" onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
