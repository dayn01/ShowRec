import { useQuery } from "@tanstack/react-query";
import { api, Status } from "../api";

const dot = (ok: boolean | null, label: string) => {
  const color = ok === null ? "#555" : ok ? "var(--green)" : "var(--red)";
  const title = ok === null ? "not configured" : ok ? "connected" : "unreachable";
  return (
    <span key={label} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--muted)" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} title={title} />
      {label}
    </span>
  );
};

export default function StatusBar() {
  const { data } = useQuery({ queryKey: ["status"], queryFn: api.getStatus, refetchInterval: 30000 });

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center", padding: "8px 0", flexWrap: "wrap" }}>
      {data ? (
        <>
          {dot(data.jellyfin, "Jellyfin")}
          {dot(data.plex, "Plex")}
          {dot(data.home_assistant, "Home Assistant")}
          {dot(data.trakt ? true : false, "Trakt")}
          {dot(data.tmdb ? true : false, "TMDB")}
        </>
      ) : (
        <span style={{ fontSize: 12, color: "var(--muted)" }}>Checking connections…</span>
      )}
    </div>
  );
}
