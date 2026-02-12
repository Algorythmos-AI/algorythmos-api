"use client";

import { useState, useEffect } from "react";
import { FileType2, Plus, Pencil, Trash2, X } from "lucide-react";
import { schemas as schemasApi } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import styles from "../shared.module.css";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SchemaItem = Record<string, any>;

export default function SchemasPage() {
    const [items, setItems] = useState<SchemaItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editItem, setEditItem] = useState<SchemaItem | null>(null);
    const [form, setForm] = useState({ name: "", description: "", fields: "[]" });
    const [error, setError] = useState<string | null>(null);

    async function load() {
        try {
            const data = await schemasApi.list(100, 0);
            setItems((data as { items: SchemaItem[] }).items || []);
        } catch { /* auth issue */ }
        setLoading(false);
    }

    useEffect(() => { load(); }, []);

    function openCreate() {
        setEditItem(null);
        setForm({ name: "", description: "", fields: "[]" });
        setShowModal(true);
    }

    function openEdit(item: SchemaItem) {
        setEditItem(item);
        setForm({
            name: item.name || "",
            description: item.description || "",
            fields: JSON.stringify(item.fields || [], null, 2),
        });
        setShowModal(true);
    }

    async function handleSave() {
        setError(null);
        let fields;
        try { fields = JSON.parse(form.fields); } catch { setError("Invalid JSON for fields"); return; }
        try {
            if (editItem) {
                await schemasApi.update(editItem.schema_id, { name: form.name, description: form.description, fields });
            } else {
                await schemasApi.create({ name: form.name, description: form.description, fields });
            }
            setShowModal(false);
            await load();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Save failed");
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Delete this schema?")) return;
        try { await schemasApi.delete(id); await load(); } catch { /* error */ }
    }

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <h1 className={styles.title}>Extraction Schemas</h1>
                    <p className={styles.subtitle}>Define what fields to extract from documents</p>
                </div>
                <button className={styles.btn} onClick={openCreate}>
                    <Plus size={14} /> New Schema
                </button>
            </div>

            <div className={styles.card}>
                {loading ? (
                    <div className={styles.cardBody}>
                        {[...Array(3)].map((_, i) => (
                            <div key={i} className={styles.skeleton} style={{ width: "100%", height: 20, marginBottom: 12 }} />
                        ))}
                    </div>
                ) : items.length > 0 ? (
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Description</th>
                                <th>Fields</th>
                                <th>Version</th>
                                <th>Updated</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((item) => (
                                <tr key={item.schema_id}>
                                    <td style={{ fontWeight: 600 }}>
                                        <FileType2 size={14} style={{ marginRight: 6, verticalAlign: -2, color: "var(--accent-primary)" }} />
                                        {item.name}
                                    </td>
                                    <td style={{ color: "var(--text-secondary)", maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                        {item.description}
                                    </td>
                                    <td>
                                        <span className={styles.badge} style={{ background: "rgba(99,102,241,0.1)", color: "var(--accent-primary)" }}>
                                            {item.fields?.length || 0} fields
                                        </span>
                                    </td>
                                    <td className={styles.mono}>v{item.version || 1}</td>
                                    <td style={{ color: "var(--text-tertiary)" }}>{timeAgo(item.updated_at || item.created_at)}</td>
                                    <td>
                                        <div className={styles.actionBtns}>
                                            <button className={styles.iconBtn} onClick={() => openEdit(item)} title="Edit">
                                                <Pencil size={14} />
                                            </button>
                                            <button className={styles.iconBtn} onClick={() => handleDelete(item.schema_id)} title="Delete">
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className={styles.emptyState}>
                        No schemas yet. Create your first extraction schema!
                    </div>
                )}
            </div>

            {/* Modal */}
            {showModal && (
                <div className={styles.modalOverlay} onClick={() => setShowModal(false)}>
                    <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                        <div className={styles.modalHeader}>
                            <span className={styles.modalTitle}>
                                {editItem ? "Edit Schema" : "New Schema"}
                            </span>
                            <button className={styles.modalClose} onClick={() => setShowModal(false)}>
                                <X size={18} />
                            </button>
                        </div>
                        <div className={styles.modalBody}>
                            {error && <div className={styles.error}>{error}</div>}
                            <div className={styles.formGroup}>
                                <label className={styles.label}>Name</label>
                                <input className={styles.input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g., Invoice Schema" />
                            </div>
                            <div className={styles.formGroup}>
                                <label className={styles.label}>Description</label>
                                <input className={styles.input} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Describe what this schema extracts" />
                            </div>
                            <div className={styles.formGroup}>
                                <label className={styles.label}>Fields (JSON)</label>
                                <textarea className={styles.textarea} value={form.fields} onChange={(e) => setForm({ ...form, fields: e.target.value })} style={{ minHeight: 200, fontFamily: "var(--font-mono)", fontSize: 12 }} />
                            </div>
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
