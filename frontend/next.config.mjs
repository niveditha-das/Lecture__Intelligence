/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No ESLint config is shipped, so don't fail `next build` on a missing one.
  eslint: { ignoreDuringBuilds: true },
};
export default nextConfig;
