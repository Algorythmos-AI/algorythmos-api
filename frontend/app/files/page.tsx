"use client";

import { useState, useEffect, useRef } from "react";
import { FileStack, CloudUpload, Trash2 } from "lucide-react";
import { files as api } from "@/lib/api";
import { timeAgo, formatBytes } from "@/lib/utils";
import styles from "../shared.module.css";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FileItem = Record<string, any>;

export default function FilesPage() {
    const [items, setItems] = useState<FileItem[]>([]);
    const [loading, setLoading] = useState(true);
    const inputRef = useRef<HTMLInputElement>(null);

    async function load() { try { const d = await api.list(100, 0); setItems((d as { items: FileItem[] }).items || []); } catch { } setLoading(false); }
    useEffect(() => { load(); }, []);

    async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
        if (!e.target.files) return;
        for (const file of Array.from(e.target.files)) {
            try { await api.upload(file); } catch { /* error */ }
        }
        await load();
    }

    async function handleDelete(id: string) { if (!confirm("Delete?")) return; try { await api.delete(id); await load(); } catch { } }

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}><h1 className={styles.title}>File Manager</h1><p className={styles.subtitle}>Upload and manage your documents</p></div>
                <button className={styles.btn} onClick={() => inputRef.current?.click()}>
                    <CloudUpload size={14} /> Upload Files
                    <input ref={inputRef} type="file" multiple style={{ display: "none" }} onChange={handleUpload} />
                </button>
            </div>
            <div className={styles.card}>
                {loading ? <div className={styles.cardBody}>{[...Array(3)].map((_, i) => <div key={i} className={styles.skeleton} style={{ width: "100%", height: 20, marginBottom: 12 }} />)}</div> : items.length > 0 ? (
                    <table className={styles.table}>
                        <thead><tr><th>Filename</th><th>Type</th><th>Size</th><th>Status</th><th>Uploaded</th><th>Actions</th></tr></thead>
                        <tbody>{items.map(item => (
                            <tr key={item.id}>
                                <td style={{ fontWeight: 600 }}><FileStack size={14} style={{ marginRight: 6, verticalAlign: -2, color: "var(--info)" }} />{item.filename}</td>
                                <td className={styles.mono}>{item.content_type || "—"}</td>
                                <td className={styles.mono}>{item.size_bytes ? formatBytes(item.size_bytes) : "—"}</td>
                                <td><span className={styles.badge} style={{ background: "var(--success-bg)", color: "var(--success)" }}>{item.status || "uploaded"}</span></td>
                                <td style={{ color: "var(--text-tertiary)" }}>{timeAgo(item.created_at)}</td>
                                <td><button className={styles.iconBtn} onClick={() => handleDelete(item.id)}><Trash2 size={14} /></button></td>
                            </tr>
                        ))}</tbody>
                    </table>
                ) : <div className={styles.emptyState}>No files uploaded yet. Click &quot;Upload Files&quot; to get started.</div>}
            </div>
        </div>
    );
}
