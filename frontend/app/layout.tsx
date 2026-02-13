import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";

export const metadata: Metadata = {
    title: "Algorythmos — Document Intelligence Platform",
    description:
        "Enterprise-grade document processing, extraction, classification, and workflow automation powered by AI.",
    icons: {
        icon: "/favicon.ico",
    },
};

import { AuthProvider } from "@/lib/auth-context";

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="en">
            <body>
                <AuthProvider>
                    <Sidebar />
                    <TopBar />
                    <main
                        style={{
                            marginLeft: "var(--sidebar-width)",
                            marginTop: "var(--topbar-height)",
                            minHeight: "calc(100vh - var(--topbar-height))",
                            padding: "var(--space-xl)",
                        }}
                    >
                        {children}
                    </main>
                </AuthProvider>
            </body>
        </html>
    );
}
