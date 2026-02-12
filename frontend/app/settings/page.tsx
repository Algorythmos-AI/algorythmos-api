"use client";

import { Settings } from "lucide-react";
import Link from "next/link";
import styles from "../shared.module.css";

export default function SettingsPage() {
    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <h1 className={styles.title}>Settings</h1>
                    <p className={styles.subtitle}>Manage your account and application settings</p>
                </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "var(--space-md)" }}>
                <Link href="/settings/api-keys" style={{ textDecoration: "none" }}>
                    <div className={styles.card} style={{ cursor: "pointer", transition: "all var(--transition-fast)" }}>
                        <div className={styles.cardBody} style={{ display: "flex", alignItems: "center", gap: "var(--space-md)" }}>
                            <Settings size={24} style={{ color: "var(--accent-primary)" }} />
                            <div>
                                <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text-primary)" }}>API Keys</div>
                                <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>Generate and manage API keys for authentication</div>
                            </div>
                        </div>
                    </div>
                </Link>
            </div>
        </div>
    );
}
