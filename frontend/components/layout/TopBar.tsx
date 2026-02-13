"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { health } from "@/lib/api";
import { capitalize } from "@/lib/utils";
import styles from "./TopBar.module.css";

import { useAuth } from "@/lib/auth-context";
import Link from "next/link";
import Image from "next/image";

export default function TopBar() {
    const pathname = usePathname();
    const [env, setEnv] = useState<string>("dev");
    const { user, logout } = useAuth();

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

                {user ? (
                    <div className={styles.userProfile} onClick={logout} title="Click to Sign Out">
                        {user.picture ? (
                            <Image
                                src={user.picture}
                                alt={user.name}
                                width={32}
                                height={32}
                                className={styles.avatar}
                            />
                        ) : (
                            <div className={styles.userAvatarFallback}>
                                {user.name?.charAt(0) || "U"}
                            </div>
                        )}
                        <span className={styles.userName}>{user.name}</span>
                    </div>
                ) : (
                    <Link href="/login" className={styles.signInBtn}>
                        Sign In
                    </Link>
                )}
            </div>
        </header>
    );
}
