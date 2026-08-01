/** @type {import('next').NextConfig} */
const nextConfig = {
  // Минимальный self-contained сервер-бандл для прод-образа (см. frontend/Dockerfile).
  output: "standalone",
};

export default nextConfig;
