/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    typedRoutes: false,
  },
  async rewrites() {
    const gateway =
      process.env.SECTION_GATEWAY_URL ?? 'http://localhost:8080';
    return [
      {
        source: '/api/gateway/:path*',
        destination: `${gateway}/:path*`,
      },
    ];
  },
};

export default nextConfig;
