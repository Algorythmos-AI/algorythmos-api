"use client";

import { useState, useEffect } from "react";
import { Tags, Plus, Pencil, Trash2, X } from "lucide-react";
import { classifiers as api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import styles from "../shared.module.css";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Item = Record<string, any>;

export default function ClassifiersPage() {
    const [items, setItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editItem, setEditItem] = useState<Item | null>(null);
    const [form, setForm] = useState({ name: "", type: "keyword", categories: "", rules: "{}", enabled: true });
    const [error, setError] = useState<string | null>(null);

    async function load() { try { const d = await api.list(100, 0); setItems((d as { items: Item[] }).items || []); } catch { } setLoading(false); }
    useEffect(() => { load(); }, []);

    function openCreate() { setEditItem(null); setForm({ name: "", type: "keyword", categories: "", rules: "{}", enabled: true }); setShowModal(true); }
    function openEdit(item: Item) { setEditItem(item); setForm({ name: item.name, type: item.type, categories: (item.categories || []).join(", "), rules: JSON.stringify(item.rules || {}, null, 2), enabled: item.enabled ?? true }); setShowModal(true); }

    async function handleSave() {
        setError(null);
        let rules; try { rules = JSON.parse(form.rules); } catch { setError("Invalid JSON for rules"); return; }
        const categories = form.categories.split(",").map(c => c.trim()).filter(Boolean);
        if (categories.length === 0) { setError("At least one category required"); return; }
        try {
            const payload = { name: form.name, type: form.type, categories, rules, enabled: form.enabled };
            if (editItem) { await api.update(editItem.classifier_id, payload); } else { await api.create(payload); }
            setShowModal(false); await load();
        } catch (e: unknown) { setError(e instanceof Error ? e.message : "Save failed"); }
    }

    async function handleDelete(id: string) { if (!confirm("Delete?")) return; try { await api.delete(id); await load(); } catch { } }

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <h1 className={styles.title}>Classifiers</h1>
                    <p className={styles.subtitle}>Classify documents into categories automatically</p>
                </div>
                <button className={styles.btn} onClick={openCreate}><Plus size={14} /> New Classifier</button>
            </div>
            <div className={styles.card}>
                {loading ? <div className={styles.cardBody}>{[...Array(3)].map((_, i) => <div key={i} className={styles.skeleton} style={{ width: "100%", height: 20, marginBottom: 12 }} />)}</div> : items.length > 0 ? (
                    <table className={styles.table}>
                        <thead><tr><th>Name</th><th>Type</th><th>Categories</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead>
                        <tbody>
                            {items.map(item => (
                                <tr key={item.classifier_id}>
                                    <td style={{ fontWeight: 600 }}><Tags size={14} style={{ marginRight: 6, verticalAlign: -2, color: "var(--accent-secondary)" }} />{item.name}</td>
                                    <td><span className={styles.badge} style={{ background: "rgba(168,85,247,0.1)", color: "var(--accent-secondary)" }}>{item.type}</span></td>
                                    <td>{(item.categories || []).slice(0, 3).map((c: string) => <span key={c} className={styles.badge} style={{ background: "var(--bg-tertiary)", marginRight: 4 }}>{c}</span>)}{(item.categories || []).length > 3 && <span style={{ color: "var(--text-tertiary)", fontSize: 11 }}>+{item.categories.length - 3}</span>}</td>
                                    <td><span className={styles.badge} style={{ background: item.enabled ? "var(--success-bg)" : "var(--danger-bg)", color: item.enabled ? "var(--success)" : "var(--danger)" }}>{item.enabled ? "Enabled" : "Disabled"}</span></td>
                                    <td style={{ color: "var(--text-tertiary)" }}>{timeAgo(item.updated_at || item.created_at)}</td>
                                    <td><div className={styles.actionBtns}><button className={styles.iconBtn} onClick={() => openEdit(item)}><Pencil size={14} /></button><button className={styles.iconBtn} onClick={() => handleDelete(item.classifier_id)}><Trash2 size={14} /></button></div></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : <div className={styles.emptyState}>No classifiers yet.</div>}
            </div>

            {showModal && (
                <div className={styles.modalOverlay} onClick={() => setShowModal(false)}>
                    <div className={styles.modal} onClick={e => e.stopPropagation()}>
                        <div className={styles.modalHeader}><span className={styles.modalTitle}>{editItem ? "Edit Classifier" : "New Classifier"}</span><button className={styles.modalClose} onClick={() => setShowModal(false)}><X size={18} /></button></div>
                        <div className={styles.modalBody}>
                            {error && <div className={styles.error}>{error}</div>}
                            <div className={styles.formGroup}><label className={styles.label}>Name</label><input className={styles.input} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
                            <div className={styles.formGroup}><label className={styles.label}>Type</label><select className={styles.select} value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}><option value="keyword">Keyword</option><option value="ml">ML</option><option value="llm">LLM</option><option value="rule_based">Rule-Based</option></select></div>
                            <div className={styles.formGroup}><label className={styles.label}>Categories (comma-separated)</label><input className={styles.input} value={form.categories} onChange={e => setForm({ ...form, categories: e.target.value })} placeholder="invoice, receipt, contract" /></div>
                            <div className={styles.formGroup}><label className={styles.label}>Rules (JSON)</label><textarea className={styles.textarea} style={{ minHeight: 150, fontFamily: "var(--font-mono)", fontSize: 12 }} value={form.rules} onChange={e => setForm({ ...form, rules: e.target.value })} /></div>
                        </div>
                        <div className={styles.modalFooter}>
                            <button className={`${styles.btn} ${styles.btnSecondary}`} onClick={() => setShowModal(false)}>Cancel</button>
                            <button className={styles.btn} onClick={handleSave}>{editItem ? "Update" : "Create"}</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
