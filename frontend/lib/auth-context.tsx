"use client";

import { GoogleOAuthProvider } from "@react-oauth/google";
import { createContext, useContext, useEffect, useState } from "react";
import { jwtDecode } from "jwt-decode";

interface User {
    name: string;
    email: string;
    picture: string;
    exp: number;
}

interface AuthContextType {
    user: User | null;
    login: (token: string) => void;
    logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);

    useEffect(() => {
        // Check local storage for existing token
        const token = localStorage.getItem("alg_id_token");
        if (token) {
            try {
                const decoded = jwtDecode<User>(token);
                if (decoded.exp * 1000 > Date.now()) {
                    setUser(decoded);
                } else {
                    localStorage.removeItem("alg_id_token");
                }
            } catch {
                localStorage.removeItem("alg_id_token");
            }
        }
    }, []);

    const login = (token: string) => {
        localStorage.setItem("alg_id_token", token);
        const decoded = jwtDecode<User>(token);
        setUser(decoded);
    };

    const logout = () => {
        localStorage.removeItem("alg_id_token");
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, login, logout }}>
            <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!}>
                {children}
            </GoogleOAuthProvider>
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
}
