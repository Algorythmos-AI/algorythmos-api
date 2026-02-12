import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    output: "standalone",
    async rewrites() {
        return [
            {
                source: "/api/:path*",
                destination: process.env.NEXT_PUBLIC_API_URL
                    ? `${process.env.NEXT_PUBLIC_API_URL}/:path*`
                    : "https://api.algorythmos.fr/api/:path*",
            },
        ];
    },
};

export default nextConfig;
