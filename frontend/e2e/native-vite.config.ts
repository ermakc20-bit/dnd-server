import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({ plugins: [react(), {
  name: "explicit-native-acceptance-entry",
  configureServer(server) {
    server.middlewares.use((request, _response, next) => {
      if (request.headers.accept?.includes("text/html") && !request.url?.startsWith("/api/")
          && !request.url?.startsWith("/__e2e/")) request.url = "/e2e/native.html";
      next();
    });
  },
}], server: { host: "127.0.0.1", port: 5189, strictPort: true,
  proxy: { "/api": { target: "http://127.0.0.1:18009", ws: true }, "/__e2e": "http://127.0.0.1:18009" } } });
