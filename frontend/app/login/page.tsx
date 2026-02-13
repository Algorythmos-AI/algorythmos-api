"use client";

import { GoogleLogin } from "@react-oauth/google";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import styles from "./login.module.css";
import Image from "next/image";

export default function LoginPage() {
    const { login, user } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (user) {
            router.push("/");
        }
    }, [user, router]);

    if (user) {
        return null;
    }

    return (
        <div className={styles.container}>
            <div className={styles.card}>
                <div className={styles.logo}>
                    <Image src="/logo.png" alt="Algorythmos" width={60} height={60} />
                </div>
                <h1 className={styles.title}>Welcome back</h1>
                <p className={styles.subtitle}>Sign in to access your dashboard</p>

                <div className={styles.googleBtn}>
                    <GoogleLogin
                        onSuccess={(credentialResponse) => {
                            if (credentialResponse.credential) {
                                login(credentialResponse.credential);
                                router.push("/");
                            }
                        }}
                        onError={() => {
                            console.log("Login Failed");
                        }}
                        theme="filled_black"
                        shape="pill"
                        width="100%"
                    />
                </div>
            </div>
        </div>
    );
}
