import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a self-contained server bundle in .next/standalone.
  // The step 0.4 Docker image copies that bundle — the build breaks without this.
  output: "standalone",
};

export default nextConfig;
