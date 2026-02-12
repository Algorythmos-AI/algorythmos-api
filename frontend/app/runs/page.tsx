"use client";

import { useState, useEffect } from "react";
import { Play, RefreshCw } from "lucide-react";
import { processorRuns } from "@/lib/api";
import { timeAgo, statusColor, formatDuration } from "@/lib/utils";
import styles from "../shared.module.css";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RunItem = Record<string, any>;

export default function RunsPage() {
    const [runs, setRuns] = useState<RunItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedRun, setSelectedRun] = useState<RunItem | null>(null);

    async function load() {
        try {
            const data = await processorRuns.list("default", 50, 0);
            setRuns((data as { items: RunItem[] }).items || []);
        } catch { /* no runs */ }
        setLoading(false);
    }

    useEffect(() => { load(); }, []);

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <h1 className={styles.title}>Processor Runs</h1>
                    <p className={styles.subtitle}>View and monitor document processing runs</p>
                </div>
                <button className={`${styles.btn} ${styles.btnSecondary}`} onClick={load}>
                    <RefreshCw size={14} /> Refresh
                </button>
            </div>

            <div className={styles.card}>
                {loading ? (
                    <div className={styles.cardBody}>
                        {[...Array(5)].map((_, i) => (
                            <div key={i} className={styles.skeleton} style={{ width: "100%", height: 20, marginBottom: 12 }} />
                        ))}
                    </div>
                ) : runs.length > 0 ? (
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>Run ID</th>
                                <th>Processor</th>
                                <th>Status</th>
                                <th>Files</th>
                                <th>Duration</th>
                                <th>Created</th>
                            </tr>
                        </thead>
                        <tbody>
                            {runs.map((run) => (
                                <tr key={run.id} onClick={() => setSelectedRun(run)} style={{ cursor: "pointer" }}>
                                    <td className={styles.mono}>{run.id?.slice(0, 12)}…</td>
                                    <td style={{ fontWeight: 600 }}>
                                        <Play size={14} style={{ marginRight: 6, verticalAlign: -2, color: "var(--accent-primary)" }} />
                                        {run.processor_name || "default"}
                                    </td>
                                    <td>
                                        <span className={styles.badge} style={{
                                            background: `color-mix(in srgb, ${statusColor(run.status)} 15%, transparent)`,
                                            color: statusColor(run.status),
                                        }}>
                                            {run.status}
                                        </span>
                                    </td>
                                    <td>{run.file_count || "—"}</td>
                                    <td className={styles.mono}>
                                        {run.processing_time_ms ? formatDuration(run.processing_time_ms) : "—"}
                                    </td>
                                    <td style={{ color: "var(--text-tertiary)" }}>{timeAgo(run.created_at)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className={styles.emptyState}>
                        No processor runs yet. Upload a document to create your first run!
                    </div>
                )}
            </div>

            {/* Run Detail Drawer */}
            {selectedRun && (
                <div className={styles.modalOverlay} onClick={() => setSelectedRun(null)}>
                    <div className={styles.modal} onClick={(e) => e.stopPropagation()} style={{ maxWidth: 700 }}>
                        <div className={styles.modalHeader}>
                            <span className={styles.modalTitle}>Run Details</span>
                            <button className={styles.modalClose} onClick={() => setSelectedRun(null)}>×</button>
                        </div>
                        <div className={styles.modalBody}>
                            <div className={styles.formGroup}>
                                <label className={styles.label}>Run ID</label>
                                <div className={styles.mono}>{selectedRun.id}</div>
                            </div>
                            <div className={styles.formGroup}>
                                <label className={styles.label}>Status</label>
                                <span className={styles.badge} style={{
                                    background: `color-mix(in srgb, ${statusColor(selectedRun.status)} 15%, transparent)`,
                                    color: statusColor(selectedRun.status),
                                }}>
                                    {selectedRun.status}
                                </span>
                            </div>
                            {selectedRun.error && (
                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Error</label>
                                    <div className={styles.error}>{selectedRun.error}</div>
                                </div>
                            )}
                            <div className={styles.formGroup}>
                                <label className={styles.label}>Result</label>
                                <pre style={{ fontFamily: "var(--font-mono)", fontSize: 11, background: "var(--bg-primary)", padding: 16, borderRadius: "var(--radius-md)", maxHeight: 400, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                    {JSON.stringify(selectedRun.result || selectedRun, null, 2)}
                                </pre>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
