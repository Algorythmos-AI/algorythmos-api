"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { health } from "@/lib/api";
import { capitalize } from "@/lib/utils";
import styles from "./TopBar.module.css";

export default function TopBar() {
    const pathname = usePathname();
    const [env, setEnv] = useState<string>("dev");

    useEffect(() => {
        health.version()
            .then((v) => setEnv(v.environment || "dev"))
            .catch(() => { });
    }, []);

    const segments = pathname.split("/").filter(Boolean);
    const pageTitle = segments.length === 0
        ? "Dashboard"
        : segments.map(s => capitalize(s.replace(/-/g, " "))).join(" / ");

    return (
        <header className={styles.topbar}>
            <div className={styles.breadcrumb}>
                <span>Algorythmos</span>
                <span>/</span>
                <span className={styles.breadcrumbCurrent}>{pageTitle}</span>
            </div>

            <div className={styles.actions}>
                <span className={`${styles.envBadge} ${styles[env]}`}>
                    {env}
                </span>
                <button className={styles.userButton} title="User menu">
                    A
                </button>
            </div>
        </header>
    );
}
