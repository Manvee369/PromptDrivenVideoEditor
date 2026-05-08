/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for the multi-stage Docker build (copies only what's needed to run).
  output: 'standalone',

  images: {
    remotePatterns: [
      // Local dev backend
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '8000',
        pathname: '/jobs/**',
      },
      // Azure Blob Storage SAS URLs (production thumbnails + downloads)
      {
        protocol: 'https',
        hostname: '*.blob.core.windows.net',
        pathname: '/**',
      },
    ],
  },

  async rewrites() {
    // In local dev, proxy /api/* to the FastAPI backend.
    // In production (Docker / Azure), nginx handles routing — this is unused.
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
