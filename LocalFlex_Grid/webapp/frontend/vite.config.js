import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Dev: /api is proxied to the FastAPI backend. Production: set VITE_API_URL at build time to the backend's public URL.
export default defineConfig({ plugins: [react()], server: { port: 5173, proxy: { "/api": process.env.VITE_DEV_API || "http://localhost:8000" } } });
