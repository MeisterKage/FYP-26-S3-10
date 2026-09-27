import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

/**
 * When the API lives on another address (as on Render), tell the browser to
 * open the connection to it while the page's own files are still downloading.
 */
function preconnectToApi(apiBase) {
  return {
    name: "preconnect-to-api",
    transformIndexHtml() {
      if (!apiBase) return [];
      return [{
        tag: "link",
        attrs: { rel: "preconnect", href: apiBase, crossorigin: "" },
        injectTo: "head",
      }];
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react(), preconnectToApi(env.VITE_API_BASE)],
    server: {
      port: 5173,
      // Flask is the single entry point (PDD 2.1), so everything goes through /api.
      proxy: { "/api": "http://127.0.0.1:5000" },
    },
  };
});
