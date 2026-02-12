"use client";

import { useState, useEffect } from "react";
import { FlaskConical, Plus, Play, Pencil, Trash2, X } from "lucide-react";
import { evaluationSets as api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import styles from "../shared.module.css";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Item = Record<string, any>;

export default function EvaluationsPage() {
    const [items, setItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editItem, setEditItem] = useState<Item | null>(null);
    const [form, setForm] = useState({ name: "", description: "", target_type: "", target_id: "" });
    const [error, setError] = useState<string | null>(null);

    async function load() { try { const d = await api.list(100, 0); setItems((d as { items: Item[] }).items || []); } catch { } setLoading(false); }
    useEffect(() => { load(); }, []);

    function openCreate() { setEditItem(null); setForm({ name: "", description: "", target_type: "", target_id: "" }); setShowModal(true); }
    function openEdit(item: Item) { setEditItem(item); setForm({ name: item.name, description: item.description || "", target_type: item.target_type || "", target_id: item.target_id || "" }); setShowModal(true); }

    async function handleSave() {
        setError(null);
        try {
            if (editItem) { await api.update(editItem.id, form); } else { await api.create(form); }
            setShowModal(false); await load();
        } catch (e: unknown) { setError(e instanceof Error ? e.message : "Save failed"); }
    }

    async function handleRun(id: string) { try { await api.run(id); alert("Evaluation started!"); } catch { alert("Failed to run evaluation"); } }
    async function handleDelete(id: string) { if (!confirm("Delete?")) return; try { await api.delete(id); await load(); } catch { } }

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}><h1 className={styles.title}>Evaluation Sets</h1><p className={styles.subtitle}>Test and benchmark your processors</p></div>
                <button className={styles.btn} onClick={openCreate}><Plus size={14} /> New Evaluation Set</button>
            </div>
            <div className={styles.card}>
                {loading ? <div className={styles.cardBody}>{[...Array(3)].map((_, i) => <div key={i} className={styles.skeleton} style={{ width: "100%", height: 20, marginBottom: 12 }} />)}</div> : items.length > 0 ? (
                    <table className={styles.table}>
                        <thead><tr><th>Name</th><th>Target</th><th>Items</th><th>Updated</th><th>Actions</th></tr></thead>
                        <tbody>{items.map(item => (
                            <tr key={item.id}>
                                <td style={{ fontWeight: 600 }}><FlaskConical size={14} style={{ marginRight: 6, verticalAlign: -2, color: "var(--success)" }} />{item.name}</td>
                                <td className={styles.mono}>{item.target_type || "—"}</td>
                                <td><span className={styles.badge} style={{ background: "var(--info-bg)", color: "var(--info)" }}>{item.item_count || 0}</span></td>
                                <td style={{ color: "var(--text-tertiary)" }}>{timeAgo(item.updated_at || item.created_at)}</td>
                                <td><div className={styles.actionBtns}><button className={styles.iconBtn} onClick={() => handleRun(item.id)} title="Run Evaluation"><Play size={14} /></button><button className={styles.iconBtn} onClick={() => openEdit(item)}><Pencil size={14} /></button><button className={styles.iconBtn} onClick={() => handleDelete(item.id)}><Trash2 size={14} /></button></div></td>
                            </tr>
                        ))}</tbody>
                    </table>
                ) : <div className={styles.emptyState}>No evaluation sets yet.</div>}
            </div>

            {showModal && (
                <div className={styles.modalOverlay} onClick={() => setShowModal(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}><span className={styles.modalTitle}>{editItem ? "Edit" : "New"} Evaluation Set</span><button className={styles.modalClose} onClick={() => setShowModal(false)}><X size={18} /></button></div>
                        <div className={styles.modalBody}>
                            {error && <div className={styles.error}>{error}</div>}
                            <div className={styles.formGroup}><label className={styles.label}>Name</label><input className={styles.input} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
                            <div className={styles.formGroup}><label className={styles.label}>Description</label><input className={styles.input} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></div>
                            <div className={styles.formGroup}><label className={styles.label}>Target Type</label><input className={styles.input} value={form.target_type} onChange={e => setForm({ ...form, target_type: e.target.value })} placeholder="e.g., processor, extractor" /></div>
                            <div className={styles.formGroup}><label className={styles.label}>Target ID</label><input className={styles.input} value={form.target_id} onChange={e => setForm({ ...form, target_id: e.target.value })} /></div>
                        </div>
                        <div className={styles.modalFooter}><button className={`${styles.btn} ${styles.btnSecondary}`} onClick={() => setShowModal(false)}>Cancel</button><button className={styles.btn} onClick={handleSave}>{editItem ? "Update" : "Create"}</button></div>
                    </div>
                </div>
            )}
        </div>
    );
}
