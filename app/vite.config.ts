import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Tauri 前端: 固定端口, 禁用清屏 (保留 Rust 报错信息)
export default defineConfig({
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  build: {
    outDir: "dist",
    target: "chrome105",
    minify: "esbuild",
    sourcemap: false,
  },
  plugins: [react()],
});
