"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    LayoutDashboard,
    Upload,
    Play,
    FileType2,
    Wrench,
    Tags,
    Scissors,
    FileStack,
    GitBranch,
    FlaskConical,
    Sparkles,
    Settings,
    Key,
} from "lucide-react";
import styles from "./Sidebar.module.css";
import { useEffect, useState } from "react";
import { health } from "@/lib/api";

const mainNav = [
    { href: "/", label: "Dashboard", icon: LayoutDashboard },
    { href: "/upload", label: "Upload & Extract", icon: Upload },
    { href: "/runs", label: "Processor Runs", icon: Play },
];

const configNav = [
    { href: "/schemas", label: "Schemas", icon: FileType2 },
    { href: "/extractors", label: "Extractors", icon: Wrench },
    { href: "/classifiers", label: "Classifiers", icon: Tags },
    { href: "/splitters", label: "Splitters", icon: Scissors },
];

const advancedNav = [
    { href: "/files", label: "Files", icon: FileStack },
    { href: "/workflows", label: "Workflows", icon: GitBranch },
    { href: "/evaluations", label: "Evaluations", icon: FlaskConical },
    { href: "/llm", label: "LLM Studio", icon: Sparkles },
];

const settingsNav = [
    { href: "/settings", label: "Settings", icon: Settings },
    { href: "/settings/api-keys", label: "API Keys", icon: Key },
];

export default function Sidebar() {
    const pathname = usePathname();
    const [apiStatus, setApiStatus] = useState<"online" | "offline" | "loading">("loading");

    useEffect(() => {
        health.check()
            .then(() => setApiStatus("online"))
            .catch(() => setApiStatus("offline"));

        const interval = setInterval(() => {
            health.check()
                .then(() => setApiStatus("online"))
                .catch(() => setApiStatus("offline"));
        }, 30_000);

        return () => clearInterval(interval);
    }, []);

    const isActive = (href: string) => {
        if (href === "/") return pathname === "/";
        return pathname.startsWith(href);
    };

    const renderNavItems = (items: typeof mainNav) =>
        items.map(({ href, label, icon: Icon }) => (
            <Link
                key={href}
                href={href}
                className={`${styles.navItem} ${isActive(href) ? styles.active : ""}`}
            >
                <Icon />
                <span>{label}</span>
            </Link>
        ));

    return (
        <aside className={styles.sidebar}>
            <div className={styles.logo}>
                <div className={styles.logoImage}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src="/logo.png" alt="Algorythmos" style={{ height: 40, width: "auto" }} />
                </div>
                <div className={styles.logoText}>
                    <span>Algorythmos</span>
                </div>
            </div>

            <nav className={styles.nav}>
                {renderNavItems(mainNav)}

                <div className={styles.section}>
                    <div className={styles.sectionLabel}>Configuration</div>
                    {renderNavItems(configNav)}
                </div>

                <div className={styles.section}>
                    <div className={styles.sectionLabel}>Advanced</div>
                    {renderNavItems(advancedNav)}
                </div>

                <div className={styles.section}>
                    <div className={styles.sectionLabel}>System</div>
                    {renderNavItems(settingsNav)}
                </div>
            </nav>

            <div className={styles.footer}>
                <div className={styles.footerText}>
                    <span
                        className={`${styles.statusDot} ${apiStatus === "offline" ? styles.statusDotOffline : ""}`}
                    />
                    API {apiStatus === "loading" ? "..." : apiStatus}
                </div>
            </div>
        </aside>
    );
}
