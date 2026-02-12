"use client";

import { useState, useEffect } from "react";
import { Scissors, Plus, Pencil, Trash2, X } from "lucide-react";
import { splitters as api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import styles from "../shared.module.css";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Item = Record<string, any>;

export default function SplittersPage() {
    const [items, setItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editItem, setEditItem] = useState<Item | null>(null);
    const [form, setForm] = useState({ name: "", type: "page", rules: "{}", enabled: true });
    const [error, setError] = useState<string | null>(null);

    async function load() { try { const d = await api.list(100, 0); setItems((d as { items: Item[] }).items || []); } catch { } setLoading(false); }
    useEffect(() => { load(); }, []);

    function openCreate() { setEditItem(null); setForm({ name: "", type: "page", rules: "{}", enabled: true }); setShowModal(true); }
    function openEdit(item: Item) { setEditItem(item); setForm({ name: item.name, type: item.type, rules: JSON.stringify(item.rules || {}, null, 2), enabled: item.enabled ?? true }); setShowModal(true); }

    async function handleSave() {
        setError(null);
        let rules; try { rules = JSON.parse(form.rules); } catch { setError("Invalid JSON"); return; }
        try {
            if (editItem) { await api.update(editItem.splitter_id, { name: form.name, type: form.type, rules, enabled: form.enabled }); } else { await api.create({ name: form.name, type: form.type, rules, enabled: form.enabled }); }
            setShowModal(false); await load();
        } catch (e: unknown) { setError(e instanceof Error ? e.message : "Save failed"); }
    }

    async function handleDelete(id: string) { if (!confirm("Delete?")) return; try { await api.delete(id); await load(); } catch { } }

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}><h1 className={styles.title}>Splitters</h1><p className={styles.subtitle}>Split documents into manageable chunks</p></div>
                <button className={styles.btn} onClick={openCreate}><Plus size={14} /> New Splitter</button>
            </div>
            <div className={styles.card}>
                {loading ? <div className={styles.cardBody}>{[...Array(3)].map((_, i) => <div key={i} className={styles.skeleton} style={{ width: "100%", height: 20, marginBottom: 12 }} />)}</div> : items.length > 0 ? (
                    <table className={styles.table}>
                        <thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead>
                        <tbody>{items.map(item => (
                            <tr key={item.splitter_id}>
                                <td style={{ fontWeight: 600 }}><Scissors size={14} style={{ marginRight: 6, verticalAlign: -2, color: "var(--warning)" }} />{item.name}</td>
                                <td><span className={styles.badge} style={{ background: "var(--warning-bg)", color: "var(--warning)" }}>{item.type}</span></td>
                                <td><span className={styles.badge} style={{ background: item.enabled ? "var(--success-bg)" : "var(--danger-bg)", color: item.enabled ? "var(--success)" : "var(--danger)" }}>{item.enabled ? "Enabled" : "Disabled"}</span></td>
                                <td style={{ color: "var(--text-tertiary)" }}>{timeAgo(item.updated_at || item.created_at)}</td>
                                <td><div className={styles.actionBtns}><button className={styles.iconBtn} onClick={() => openEdit(item)}><Pencil size={14} /></button><button className={styles.iconBtn} onClick={() => handleDelete(item.splitter_id)}><Trash2 size={14} /></button></div></td>
                            </tr>
                        ))}</tbody>
                    </table>
                ) : <div className={styles.emptyState}>No splitters yet.</div>}
            </div>
            {showModal && (
                <div className={styles.modalOverlay} onClick={() => setShowModal(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}><span className={styles.modalTitle}>{editItem ? "Edit" : "New"} Splitter</span><button className={styles.modalClose} onClick={() => setShowModal(false)}><X size={18} /></button></div>
                        <div className={styles.modalBody}>
                            {error && <div className={styles.error}>{error}</div>}
                            <div className={styles.formGroup}><label className={styles.label}>Name</label><input className={styles.input} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
                            <div className={styles.formGroup}><label className={styles.label}>Type</label><select className={styles.select} value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}><option value="page">Page</option><option value="section">Section</option><option value="pattern">Pattern</option><option value="size">Size</option></select></div>
                            <div className={styles.formGroup}><label className={styles.label}>Rules (JSON)</label><textarea className={styles.textarea} style={{ minHeight: 150, fontFamily: "var(--font-mono)", fontSize: 12 }} value={form.rules} onChange={e => setForm({ ...form, rules: e.target.value })} /></div>
                        </div>
                        <div className={styles.modalFooter}><button className={`${styles.btn} ${styles.btnSecondary}`} onClick={() => setShowModal(false)}>Cancel</button><button className={styles.btn} onClick={handleSave}>{editItem ? "Update" : "Create"}</button></div>
                    </div>
                </div>
            )}
        </div>
    );
}
