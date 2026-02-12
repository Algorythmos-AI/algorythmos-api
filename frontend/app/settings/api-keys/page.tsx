"use client";

import { useState, useEffect } from "react";
import { Key, Plus, Copy, Check, Save } from "lucide-react";
import { auth } from "@/lib/api";
import { timeAgo, copyToClipboard } from "@/lib/utils";
import styles from "./apikeys.module.css";

interface ApiKeyItem {
    id: string;
    name: string;
    prefix: string;
    is_active: boolean;
    created_at: string;
    last_used_at: string | null;
}

export default function ApiKeysPage() {
    const [keys, setKeys] = useState<ApiKeyItem[]>([]);
    const [newKeyName, setNewKeyName] = useState("");
    const [newRawKey, setNewRawKey] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState(false);
    const [localKey, setLocalKey] = useState("");
    const [savedMsg, setSavedMsg] = useState(false);

    useEffect(() => {
        if (typeof window !== "undefined") {
            setLocalKey(localStorage.getItem("alg_api_key") || "");
        }
        loadKeys();
    }, []);

    async function loadKeys() {
        try {
            const data = await auth.listApiKeys();
            setKeys(data.items || []);
        } catch { /* not authenticated */ }
    }

    async function handleCreate() {
        if (!newKeyName.trim()) return;
        setLoading(true);
        try {
            const data = await auth.createApiKey(newKeyName);
            setNewRawKey(data.raw_key);
            setNewKeyName("");
            await loadKeys();
        } catch { /* error */ }
        setLoading(false);
    }

    async function handleRevoke(id: string) {
        if (!confirm("Revoke this API key? This cannot be undone.")) return;
        try {
            await auth.revokeApiKey(id);
            await loadKeys();
        } catch { /* error */ }
    }

    async function handleCopy() {
        if (newRawKey) {
            await copyToClipboard(newRawKey);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    }

    function handleSaveLocal() {
        localStorage.setItem("alg_api_key", localKey);
        setSavedMsg(true);
        setTimeout(() => setSavedMsg(false), 2000);
    }

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <h1 className={styles.title}>API Keys</h1>
                <p className={styles.subtitle}>
                    Manage your API keys for authenticating with the Algorythmos API
                </p>
            </div>

            {/* Local API Key Setting */}
            <div className={styles.apiKeyInput}>
                <input
                    className={styles.input}
                    type="password"
                    placeholder="Enter your API key (alg_...)"
                    value={localKey}
                    onChange={(e) => setLocalKey(e.target.value)}
                />
                <button className={styles.saveBtn} onClick={handleSaveLocal}>
                    <Save size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
                    {savedMsg ? "Saved!" : "Save to Browser"}
                </button>
            </div>

            {/* New Key Banner */}
            {newRawKey && (
                <div className={styles.newKeyBanner}>
                    <p>
                        <strong>⚠️ Copy your new API key now!</strong> It won&apos;t be shown again.
                    </p>
                    <div className={styles.keyDisplay}>
                        <span className={styles.keyText}>{newRawKey}</span>
                        <button className={styles.copyBtn} onClick={handleCopy}>
                            {copied ? <Check size={12} /> : <Copy size={12} />}
                            {copied ? "Copied" : "Copy"}
                        </button>
                    </div>
                </div>
            )}

            {/* Create Key */}
            <div className={styles.inputGroup}>
                <input
                    className={styles.input}
                    placeholder="Key name (e.g., Production Frontend)"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                />
                <button
                    className={styles.btn}
                    disabled={!newKeyName.trim() || loading}
                    onClick={handleCreate}
                >
                    <Plus size={14} />
                    Generate Key
                </button>
            </div>

            {/* Key List */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <span className={styles.cardTitle}>
                        <Key size={16} style={{ marginRight: 8, verticalAlign: -2 }} />
                        Your API Keys
                    </span>
                </div>
                {keys.length > 0 ? (
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Prefix</th>
                                <th>Status</th>
                                <th>Created</th>
                                <th>Last Used</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {keys.map((k) => (
                                <tr key={k.id}>
                                    <td style={{ fontWeight: 600 }}>{k.name}</td>
                                    <td className={styles.mono}>{k.prefix}…</td>
                                    <td>
                                        <span
                                            className={styles.badge}
                                            style={{
                                                background: k.is_active ? "var(--success-bg)" : "var(--danger-bg)",
                                                color: k.is_active ? "var(--success)" : "var(--danger)",
                                            }}
                                        >
                                            {k.is_active ? "Active" : "Revoked"}
                                        </span>
                                    </td>
                                    <td style={{ color: "var(--text-tertiary)" }}>
                                        {timeAgo(k.created_at)}
                                    </td>
                                    <td style={{ color: "var(--text-tertiary)" }}>
                                        {k.last_used_at ? timeAgo(k.last_used_at) : "Never"}
                                    </td>
                                    <td>
                                        {k.is_active && (
                                            <button
                                                className={styles.revokeBtn}
                                                onClick={() => handleRevoke(k.id)}
                                            >
                                                Revoke
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className={styles.emptyState}>
                        No API keys yet. Generate one above.
                    </div>
                )}
            </div>
        </div>
    );
}
