import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Flask is the single entry point (PDD 2.1), so everything goes through /api.
    proxy: { "/api": "http://127.0.0.1:5000" },
  },
});
