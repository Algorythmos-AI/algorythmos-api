"use client";

import { useState } from "react";
import { Sparkles, FileText, Users, MessageSquare, Copy, Check } from "lucide-react";
import { llm } from "@/lib/api";
import { copyToClipboard } from "@/lib/utils";
import styles from "../shared.module.css";

type Tab = "summarize" | "entities" | "qa";

export default function LLMStudioPage() {
    const [tab, setTab] = useState<Tab>("summarize");
    const [text, setText] = useState("");
    const [questions, setQuestions] = useState("");
    const [maxLength, setMaxLength] = useState(500);
    const [style, setStyle] = useState("concise");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const [result, setResult] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);

    async function handleRun() {
        if (!text.trim()) return;
        setLoading(true); setError(null); setResult(null);
        try {
            if (tab === "summarize") {
                const r = await llm.summarize(text, maxLength, style);
                setResult(r);
            } else if (tab === "entities") {
                const r = await llm.extractEntities(text);
                setResult(r);
            } else {
                const qs = questions.split("\n").filter(q => q.trim());
                const r = await llm.answerQuestions(text, qs);
                setResult(r);
            }
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "LLM request failed");
        }
        setLoading(false);
    }

    async function handleCopy() {
        await copyToClipboard(JSON.stringify(result, null, 2));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    const tabs: { id: Tab; label: string; icon: typeof Sparkles }[] = [
        { id: "summarize", label: "Summarize", icon: FileText },
        { id: "entities", label: "Entities", icon: Users },
        { id: "qa", label: "Q&A", icon: MessageSquare },
    ];

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <h1 className={styles.title}>
                        <Sparkles size={24} style={{ marginRight: 8, verticalAlign: -4, color: "var(--accent-secondary)" }} />
                        LLM Studio
                    </h1>
                    <p className={styles.subtitle}>AI-powered document analysis — summarize, extract entities, and answer questions</p>
                </div>
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", gap: 2, background: "var(--bg-tertiary)", borderRadius: "var(--radius-md)", padding: 3, marginBottom: "var(--space-xl)", width: "fit-content" }}>
                {tabs.map(t => (
                    <button
                        key={t.id}
                        onClick={() => { setTab(t.id); setResult(null); }}
                        style={{
                            padding: "10px 20px", borderRadius: "var(--radius-sm)", border: "none",
                            background: tab === t.id ? "var(--bg-quaternary)" : "transparent",
                            color: tab === t.id ? "var(--text-primary)" : "var(--text-secondary)",
                            font: "inherit", fontSize: 13, fontWeight: 600, cursor: "pointer",
                            display: "flex", alignItems: "center", gap: 6,
                            transition: "all var(--transition-fast)",
                        }}
                    >
                        <t.icon size={14} /> {t.label}
                    </button>
                ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-xl)" }}>
                {/* Input */}
                <div>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Document Text</label>
                        <textarea
                            className={styles.textarea}
                            style={{ minHeight: 300, fontFamily: "var(--font-mono)", fontSize: 12 }}
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            placeholder="Paste your document text here..."
                        />
                    </div>

                    {tab === "summarize" && (
                        <div style={{ display: "flex", gap: "var(--space-md)" }}>
                            <div className={styles.formGroup} style={{ flex: 1 }}>
                                <label className={styles.label}>Max Length</label>
                                <input className={styles.input} type="number" value={maxLength} onChange={(e) => setMaxLength(Number(e.target.value))} />
                            </div>
                            <div className={styles.formGroup} style={{ flex: 1 }}>
                                <label className={styles.label}>Style</label>
                                <select className={styles.select} value={style} onChange={(e) => setStyle(e.target.value)}>
                                    <option value="concise">Concise</option>
                                    <option value="detailed">Detailed</option>
                                    <option value="bullet_points">Bullet Points</option>
                                </select>
                            </div>
                        </div>
                    )}

                    {tab === "qa" && (
                        <div className={styles.formGroup}>
                            <label className={styles.label}>Questions (one per line)</label>
                            <textarea
                                className={styles.textarea}
                                style={{ minHeight: 100 }}
                                value={questions}
                                onChange={(e) => setQuestions(e.target.value)}
                                placeholder="What is the total amount?&#10;Who is the vendor?"
                            />
                        </div>
                    )}

                    <button className={styles.btn} onClick={handleRun} disabled={!text.trim() || loading} style={{ width: "100%" }}>
                        <Sparkles size={14} /> {loading ? "Processing…" : "Run AI Analysis"}
                    </button>
                </div>

                {/* Output */}
                <div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--space-md)" }}>
                        <label className={styles.label}>Results</label>
                        {result && (
                            <button onClick={handleCopy} style={{ background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "4px 10px", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                                {copied ? <Check size={10} /> : <Copy size={10} />} {copied ? "Copied" : "Copy"}
                            </button>
                        )}
                    </div>
                    {error && <div className={styles.error}>{error}</div>}

                    <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", minHeight: 300, padding: "var(--space-lg)" }}>
                        {loading ? (
                            <div style={{ textAlign: "center", paddingTop: 60 }}>
                                <div style={{ width: 30, height: 30, border: "3px solid var(--border)", borderTopColor: "var(--accent-primary)", borderRadius: "50%", animation: "spin 0.8s linear infinite", margin: "0 auto 12px" }} />
                                <div style={{ color: "var(--text-tertiary)", fontSize: 13 }}>AI is analyzing...</div>
                            </div>
                        ) : result ? (
                            <pre style={{ fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.8, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                                {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
                            </pre>
                        ) : (
                            <div style={{ textAlign: "center", paddingTop: 80, color: "var(--text-tertiary)", fontSize: 13 }}>
                                Results will appear here
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
