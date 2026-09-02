import { defineConfig, type Plugin, type ViteDevServer } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

function sharedAuthEntry(): Plugin {
  return {
    name: "openhdo-auth-entry",
    configureServer(server: ViteDevServer) {
      server.middlewares.use((request, _response, next) => {
        const requestWithUrl = request as typeof request & { url?: string };
        const url = requestWithUrl.url;
        if (url === "/" || url?.startsWith("/?")) {
          requestWithUrl.url = `/admin/${url.slice(1)}`;
        } else if (url === "/auth" || url?.startsWith("/auth/") || url?.startsWith("/auth?")) {
          requestWithUrl.url = `/admin/${url.slice("/auth".length).replace(/^\/?/, "")}`;
        }
        next();
      });
    },
  };
}

export default defineConfig({
  base: "/admin/",
  plugins: [sharedAuthEntry(), react(), tailwindcss()],
  server: {
    port: 4173,
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8000" } },
  },
});
