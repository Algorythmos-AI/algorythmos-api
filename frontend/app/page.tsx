"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
    Activity,
    Upload,
    Play,
    FileType2,
    Zap,
    CheckCircle2,
    Clock,
    AlertTriangle,
} from "lucide-react";
import { health, processorRuns, schemas } from "@/lib/api";
import { timeAgo, statusColor } from "@/lib/utils";
import styles from "./dashboard.module.css";

interface HealthData {
    status: string;
    database: string;
    redis: string;
    environment: string;
}

interface VersionData {
    version: string;
    api_name: string;
    environment: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RunItem = Record<string, any>;

export default function DashboardPage() {
    const [healthData, setHealthData] = useState<HealthData | null>(null);
    const [versionData, setVersionData] = useState<VersionData | null>(null);
    const [recentRuns, setRecentRuns] = useState<RunItem[]>([]);
    const [schemaCount, setSchemaCount] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function load() {
            try {
                const [h, v] = await Promise.allSettled([
                    health.check(),
                    health.version(),
                ]);
                if (h.status === "fulfilled") setHealthData(h.value as HealthData);
                if (v.status === "fulfilled") setVersionData(v.value as VersionData);

                // Try to load runs and schemas
                try {
                    const runs = await processorRuns.list("default", 5, 0);
                    setRecentRuns((runs as { items: RunItem[] }).items || []);
                } catch { /* May not have any runs yet */ }

                try {
                    const s = await schemas.list(1, 0);
                    setSchemaCount((s as { total: number }).total || 0);
                } catch { /* API key might not be set */ }
            } finally {
                setLoading(false);
            }
        }
        load();
    }, []);

    const metrics = [
        {
            label: "API Status",
            value: healthData?.status === "healthy" ? "Online" : loading ? "..." : "Offline",
            icon: Activity,
            color: healthData?.status === "healthy" ? "var(--success)" : "var(--danger)",
            bg: healthData?.status === "healthy" ? "var(--success-bg)" : "var(--danger-bg)",
        },
        {
            label: "Total Runs",
            value: recentRuns.length > 0 ? `${recentRuns.length}+` : "—",
            icon: Play,
            color: "var(--accent-primary)",
            bg: "rgba(99, 102, 241, 0.1)",
        },
        {
            label: "Schemas",
            value: schemaCount !== null ? String(schemaCount) : "—",
            icon: FileType2,
            color: "var(--accent-secondary)",
            bg: "rgba(168, 85, 247, 0.1)",
        },
        {
            label: "Version",
            value: versionData?.version || "—",
            icon: Zap,
            color: "var(--warning)",
            bg: "var(--warning-bg)",
        },
    ];

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <h1 className={styles.title}>
                    Welcome to <span className="gradient-text">Algorythmos</span>
                </h1>
                <p className={styles.subtitle}>
                    Document intelligence platform — extract, classify, and process at scale
                </p>
            </div>

            {/* Quick Actions */}
            <div className={styles.quickActions}>
                <Link href="/upload" className={styles.actionBtn}>
                    <Upload size={20} />
                    Upload & Extract
                </Link>
                <Link href="/runs" className={styles.actionBtn}>
                    <Play size={20} />
                    View Runs
                </Link>
                <Link href="/schemas" className={styles.actionBtn}>
                    <FileType2 size={20} />
                    Manage Schemas
                </Link>
                <Link href="/settings/api-keys" className={styles.actionBtn}>
                    <Zap size={20} />
                    API Keys
                </Link>
            </div>

            {/* Metric Cards */}
            <div className={styles.metricsGrid}>
                {metrics.map((m) => (
                    <div key={m.label} className={styles.metricCard}>
                        <div
                            className={styles.metricIcon}
                            style={{ background: m.bg, color: m.color }}
                        >
                            <m.icon size={20} />
                        </div>
                        <div className={styles.metricValue} style={{ color: m.color }}>
                            {m.value}
                        </div>
                        <div className={styles.metricLabel}>{m.label}</div>
                    </div>
                ))}
            </div>

            {/* Two-column section */}
            <div className={styles.sectionGrid}>
                {/* Recent Runs */}
                <div className={styles.card}>
                    <div className={styles.cardHeader}>
                        <span className={styles.cardTitle}>Recent Processor Runs</span>
                        <Link href="/runs" style={{ fontSize: 12, fontWeight: 600 }}>
                            View All →
                        </Link>
                    </div>
                    <div className={styles.cardBody} style={{ padding: 0 }}>
                        {recentRuns.length > 0 ? (
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Run ID</th>
                                        <th>Status</th>
                                        <th>Time</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {recentRuns.map((run) => (
                                        <tr key={run.id}>
                                            <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                                                {run.id?.slice(0, 12)}…
                                            </td>
                                            <td>
                                                <span
                                                    className={styles.badge}
                                                    style={{
                                                        background: `color-mix(in srgb, ${statusColor(run.status)} 15%, transparent)`,
                                                        color: statusColor(run.status),
                                                    }}
                                                >
                                                    <span
                                                        className={styles.badgeDot}
                                                        style={{ background: statusColor(run.status) }}
                                                    />
                                                    {run.status}
                                                </span>
                                            </td>
                                            <td style={{ color: "var(--text-tertiary)", fontSize: 12 }}>
                                                {timeAgo(run.created_at)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            <div className={styles.emptyState}>
                                <p>No runs yet. Upload your first document!</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Health Status */}
                <div className={styles.card}>
                    <div className={styles.cardHeader}>
                        <span className={styles.cardTitle}>System Health</span>
                    </div>
                    <div className={styles.cardBody}>
                        {healthData ? (
                            <div className={styles.healthGrid}>
                                <div className={styles.healthRow}>
                                    <span className={styles.healthLabel}>
                                        <CheckCircle2 size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
                                        API
                                    </span>
                                    <span
                                        className={styles.healthValue}
                                        style={{ color: statusColor(healthData.status) }}
                                    >
                                        {healthData.status}
                                    </span>
                                </div>
                                <div className={styles.healthRow}>
                                    <span className={styles.healthLabel}>
                                        <CheckCircle2 size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
                                        Database
                                    </span>
                                    <span
                                        className={styles.healthValue}
                                        style={{ color: statusColor(healthData.database) }}
                                    >
                                        {healthData.database}
                                    </span>
                                </div>
                                <div className={styles.healthRow}>
                                    <span className={styles.healthLabel}>
                                        <Clock size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
                                        Redis
                                    </span>
                                    <span
                                        className={styles.healthValue}
                                        style={{ color: statusColor(healthData.redis) }}
                                    >
                                        {healthData.redis}
                                    </span>
                                </div>
                                <div className={styles.healthRow}>
                                    <span className={styles.healthLabel}>
                                        <AlertTriangle size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
                                        Environment
                                    </span>
                                    <span className={styles.healthValue}>
                                        {healthData.environment}
                                    </span>
                                </div>
                                {versionData && (
                                    <>
                                        <div className={styles.healthRow}>
                                            <span className={styles.healthLabel}>Version</span>
                                            <span className={styles.healthValue}>
                                                {versionData.version}
                                            </span>
                                        </div>
                                        <div className={styles.healthRow}>
                                            <span className={styles.healthLabel}>API Name</span>
                                            <span className={styles.healthValue}>
                                                {versionData.api_name}
                                            </span>
                                        </div>
                                    </>
                                )}
                            </div>
                        ) : (
                            <div className={styles.emptyState}>
                                {loading ? (
                                    <div>
                                        <div className={styles.skeleton} style={{ width: "100%", height: 20, marginBottom: 12 }} />
                                        <div className={styles.skeleton} style={{ width: "80%", height: 20, marginBottom: 12 }} />
                                        <div className={styles.skeleton} style={{ width: "60%", height: 20 }} />
                                    </div>
                                ) : (
                                    <p>Unable to reach API. Check your API key in Settings.</p>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
