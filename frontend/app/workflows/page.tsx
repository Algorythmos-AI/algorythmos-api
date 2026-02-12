"use client";

import { useState, useEffect } from "react";
import { GitBranch, Plus, Play, Pencil, Trash2, X } from "lucide-react";
import { workflows as api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import styles from "../shared.module.css";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Item = Record<string, any>;

export default function WorkflowsPage() {
    const [items, setItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editItem, setEditItem] = useState<Item | null>(null);
    const [form, setForm] = useState({ name: "", description: "", steps: "[]", enabled: true });
    const [error, setError] = useState<string | null>(null);

    async function load() { try { const d = await api.list(100, 0); setItems((d as { items: Item[] }).items || []); } catch { } setLoading(false); }
    useEffect(() => { load(); }, []);

    function openCreate() { setEditItem(null); setForm({ name: "", description: "", steps: "[]", enabled: true }); setShowModal(true); }
    function openEdit(item: Item) { setEditItem(item); setForm({ name: item.name, description: item.description || "", steps: JSON.stringify(item.steps || [], null, 2), enabled: item.enabled ?? true }); setShowModal(true); }

    async function handleSave() {
        setError(null);
        let steps; try { steps = JSON.parse(form.steps); } catch { setError("Invalid JSON"); return; }
        try {
            if (editItem) { await api.update(editItem.id, { name: form.name, description: form.description, steps, enabled: form.enabled }); } else { await api.create({ name: form.name, description: form.description, steps, enabled: form.enabled }); }
            setShowModal(false); await load();
        } catch (e: unknown) { setError(e instanceof Error ? e.message : "Save failed"); }
    }

    async function handleExecute(id: string) { try { await api.execute(id); alert("Workflow executed!"); } catch { alert("Execution failed"); } }
    async function handleDelete(id: string) { if (!confirm("Delete?")) return; try { await api.delete(id); await load(); } catch { } }

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}><h1 className={styles.title}>Workflows</h1><p className={styles.subtitle}>Chain processors into automated pipelines</p></div>
                <button className={styles.btn} onClick={openCreate}><Plus size={14} /> New Workflow</button>
            </div>
            <div className={styles.card}>
                {loading ? <div className={styles.cardBody}>{[...Array(3)].map((_, i) => <div key={i} className={styles.skeleton} style={{ width: "100%", height: 20, marginBottom: 12 }} />)}</div> : items.length > 0 ? (
                    <table className={styles.table}>
                        <thead><tr><th>Name</th><th>Steps</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead>
                        <tbody>{items.map(item => (
                            <tr key={item.id}>
                                <td style={{ fontWeight: 600 }}><GitBranch size={14} style={{ marginRight: 6, verticalAlign: -2, color: "var(--accent-primary)" }} />{item.name}</td>
                                <td><span className={styles.badge} style={{ background: "rgba(99,102,241,0.1)", color: "var(--accent-primary)" }}>{item.steps?.length || 0} steps</span></td>
                                <td><span className={styles.badge} style={{ background: item.enabled ? "var(--success-bg)" : "var(--danger-bg)", color: item.enabled ? "var(--success)" : "var(--danger)" }}>{item.enabled ? "Enabled" : "Disabled"}</span></td>
                                <td style={{ color: "var(--text-tertiary)" }}>{timeAgo(item.updated_at || item.created_at)}</td>
                                <td><div className={styles.actionBtns}><button className={styles.iconBtn} onClick={() => handleExecute(item.id)} title="Execute"><Play size={14} /></button><button className={styles.iconBtn} onClick={() => openEdit(item)}><Pencil size={14} /></button><button className={styles.iconBtn} onClick={() => handleDelete(item.id)}><Trash2 size={14} /></button></div></td>
                            </tr>
                        ))}</tbody>
                    </table>
                ) : <div className={styles.emptyState}>No workflows yet.</div>}
            </div>

            {showModal && (
                <div className={styles.modalOverlay} onClick={() => setShowModal(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}><span className={styles.modalTitle}>{editItem ? "Edit" : "New"} Workflow</span><button className={styles.modalClose} onClick={() => setShowModal(false)}><X size={18} /></button></div>
                        <div className={styles.modalBody}>
                            {error && <div className={styles.error}>{error}</div>}
                            <div className={styles.formGroup}><label className={styles.label}>Name</label><input className={styles.input} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
                            <div className={styles.formGroup}><label className={styles.label}>Description</label><input className={styles.input} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></div>
                            <div className={styles.formGroup}><label className={styles.label}>Steps (JSON)</label><textarea className={styles.textarea} style={{ minHeight: 200, fontFamily: "var(--font-mono)", fontSize: 12 }} value={form.steps} onChange={e => setForm({ ...form, steps: e.target.value })} /></div>
                        </div>
                        <div className={styles.modalFooter}><button className={`${styles.btn} ${styles.btnSecondary}`} onClick={() => setShowModal(false)}>Cancel</button><button className={styles.btn} onClick={handleSave}>{editItem ? "Update" : "Create"}</button></div>
                    </div>
                </div>
            )}
        </div>
    );
}
