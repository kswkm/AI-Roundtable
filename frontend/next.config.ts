import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ESLint는 쓰지 않는다. 타입 검사는 npm run typecheck로 한다.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
