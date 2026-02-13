import type { NextConfig } from "next";

const apiBaseUrl = (
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://api.algorythmos.com/api"
).replace(/\/+$/, "");

const nextConfig: NextConfig = {
    output: "standalone",
    async rewrites() {
        return [
            {
                source: "/api/:path*",
                destination: `${apiBaseUrl}/:path*`,
            },
        ];
    },
    images: {
        remotePatterns: [
            { protocol: "https", hostname: "lh3.googleusercontent.com" },
            { protocol: "https", hostname: "googleusercontent.com" },
        ],
    },
};

export default nextConfig;
