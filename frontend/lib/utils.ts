/* ============================================================
   Algorythmos — Utility Helpers
   ============================================================ */

/** Format bytes to human-readable size */
export function formatBytes(bytes: number): string {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/** Format milliseconds to human-readable duration */
export function formatDuration(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

/** Format ISO date to relative time string */
export function timeAgo(dateStr: string): string {
    const now = Date.now();
    const d = new Date(dateStr).getTime();
    const diff = now - d;
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(dateStr).toLocaleDateString();
}

/** Truncate a string to max length with ellipsis */
export function truncate(str: string, max: number): string {
    if (str.length <= max) return str;
    return str.slice(0, max - 1) + "…";
}

/** Capitalize first letter */
export function capitalize(s: string): string {
    return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Status color mapping */
export function statusColor(status: string): string {
    const map: Record<string, string> = {
        succeeded: "var(--success)",
        completed: "var(--success)",
        healthy: "var(--success)",
        active: "var(--success)",
        running: "var(--info)",
        processing: "var(--info)",
        pending: "var(--warning)",
        queued: "var(--warning)",
        failed: "var(--danger)",
        cancelled: "var(--text-tertiary)",
        revoked: "var(--text-tertiary)",
    };
    return map[status?.toLowerCase()] || "var(--text-secondary)";
}

/** Generate a random short ID for client-side use */
export function uid(): string {
    return Math.random().toString(36).slice(2, 10);
}

/** Safely parse JSON or return null */
export function safeParseJSON(str: string): unknown {
    try { return JSON.parse(str); } catch { return null; }
}

/** Copy text to clipboard */
export async function copyToClipboard(text: string): Promise<boolean> {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        return false;
    }
}
