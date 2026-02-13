"use client";

import { useRef, useState, useCallback } from "react";
import {
    CloudUpload,
    FileText,
    X,
    Zap,
    Copy,
    Check,
} from "lucide-react";
import { extract, ApiError } from "@/lib/api";
import { formatBytes, copyToClipboard } from "@/lib/utils";
import styles from "./upload.module.css";

export default function UploadPage() {
    const inputRef = useRef<HTMLInputElement>(null);
    const [files, setFiles] = useState<File[]>([]);
    const [provider, setProvider] = useState("");
    const [processing, setProcessing] = useState(false);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);
    const [dragActive, setDragActive] = useState(false);
    const [viewMode, setViewMode] = useState<"json" | "table">("json");
    const [copied, setCopied] = useState(false);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setDragActive(false);
        const dropped = Array.from(e.dataTransfer.files).filter(
            (f) => f.type === "application/pdf"
        );
        setFiles((prev) => [...prev, ...dropped]);
    }, []);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
        }
    };

    const removeFile = (idx: number) => {
        setFiles((prev) => prev.filter((_, i) => i !== idx));
    };

    const handleExtract = async () => {
        if (files.length === 0) return;
        setProcessing(true);
        setError(null);
        setResult(null);

        try {
            const data = await extract.upload(
                files,
                provider || undefined
            );
            setResult(data);
        } catch (err: unknown) {
            if (err instanceof ApiError) {
                setError(`[${err.code}] ${err.message}`);
            } else {
                const msg = err instanceof Error ? err.message : "Extraction failed";
                setError(msg);
            }
        } finally {
            setProcessing(false);
        }
    };

    const handleCopy = async () => {
        if (result) {
            await copyToClipboard(JSON.stringify(result, null, 2));
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const renderTable = (data: any) => {
        if (!data) return null;
        const records = data.records || data.results || (Array.isArray(data) ? data : [data]);
        if (records.length === 0) return <div className={styles.jsonView}>No records found</div>;

        const keys = Object.keys(records[0] || {});
        return (
            <div style={{ overflowX: "auto" }}>
                <table className={styles.jsonView} style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                        <tr>
                            {keys.map((k) => (
                                <th
                                    key={k}
                                    style={{
                                        textAlign: "left",
                                        padding: "8px 12px",
                                        borderBottom: "1px solid var(--border)",
                                        fontSize: 11,
                                        fontWeight: 700,
                                        textTransform: "uppercase",
                                        letterSpacing: "0.06em",
                                        color: "var(--text-tertiary)",
                                    }}
                                >
                                    {k}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {records.map((r: any, i: number) => (
                            <tr key={i}>
                                {keys.map((k) => (
                                    <td
                                        key={k}
                                        style={{
                                            padding: "8px 12px",
                                            borderBottom: "1px solid rgba(148,163,184,0.06)",
                                            fontSize: 12,
                                        }}
                                    >
                                        {typeof r[k] === "object" ? JSON.stringify(r[k]) : String(r[k] ?? "")}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div>
                    <h1 className={styles.title}>Upload & Extract</h1>
                    <p className={styles.subtitle}>
                        Drop PDF files to extract structured data using Algorythmos AI
                    </p>
                </div>
            </div>

            {/* Drop Zone */}
            <div
                className={`${styles.dropZone} ${dragActive ? styles.dropZoneActive : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
            >
                <CloudUpload size={48} className={styles.dropIcon} />
                <div className={styles.dropText}>
                    Drop PDF files here or click to browse
                </div>
                <div className={styles.dropHint}>
                    Supports PDF files up to 10MB each, max 50 files
                </div>
                <input
                    ref={inputRef}
                    type="file"
                    accept=".pdf"
                    multiple
                    className={styles.hiddenInput}
                    onChange={handleFileChange}
                />
            </div>

            {/* Selected Files */}
            {files.length > 0 && (
                <div className={styles.fileList}>
                    {files.map((f, i) => (
                        <div key={i} className={styles.fileItem}>
                            <FileText size={18} />
                            <span className={styles.fileName}>{f.name}</span>
                            <span className={styles.fileSize}>{formatBytes(f.size)}</span>
                            <button className={styles.removeBtn} onClick={() => removeFile(i)}>
                                <X size={14} />
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {/* Options */}
            <div className={styles.optionsRow}>
                <select
                    className={styles.select}
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                >
                    <option value="">Auto-detect provider</option>
                    <option value="google">Google Vision OCR</option>
                    <option value="orange">Orange</option>
                    <option value="generic_telco">Generic Telco</option>
                </select>

                <button
                    className={styles.extractBtn}
                    disabled={files.length === 0 || processing}
                    onClick={handleExtract}
                >
                    <Zap size={16} />
                    {processing ? "Processing…" : "Extract Data"}
                </button>
            </div>

            {/* Error */}
            {error && <div className={styles.error}>{error}</div>}

            {/* Processing */}
            {processing && (
                <div className={styles.processing}>
                    <div className={styles.spinner} />
                    <div className={styles.processingText}>
                        Processing {files.length} file{files.length > 1 ? "s" : ""}…
                    </div>
                </div>
            )}

            {/* Results */}
            {result && !processing && (
                <div className={styles.results}>
                    <div className={styles.resultHeader}>
                        <h2 className={styles.resultTitle}>Extraction Results</h2>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <div className={styles.tabBar}>
                                <button
                                    className={`${styles.tab} ${viewMode === "json" ? styles.tabActive : ""}`}
                                    onClick={() => setViewMode("json")}
                                >
                                    JSON
                                </button>
                                <button
                                    className={`${styles.tab} ${viewMode === "table" ? styles.tabActive : ""}`}
                                    onClick={() => setViewMode("table")}
                                >
                                    Table
                                </button>
                            </div>
                            <button className={styles.copyBtn} onClick={handleCopy}>
                                {copied ? <Check size={12} /> : <Copy size={12} />}
                                {copied ? "Copied!" : "Copy"}
                            </button>
                        </div>
                    </div>

                    {viewMode === "json" ? (
                        <pre className={styles.jsonView}>
                            {JSON.stringify(result, null, 2)}
                        </pre>
                    ) : (
                        renderTable(result)
                    )}
                </div>
            )}
        </div>
    );
}
