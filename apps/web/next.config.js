/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: false
  },
  webpack: (config) => {
    config.resolve.fallback = {
      ...(config.resolve.fallback || {}),
      canvas: false
    };
    return config;
  }
};

module.exports = nextConfig;
