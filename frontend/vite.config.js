import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [
    vue(),
    {
      name: "runtime-configuration",
      transformIndexHtml: {
        order: "post",
        handler() {
          return [
            {
              tag: "script",
              attrs: { src: "/runtime-config.js" },
              injectTo: "head-prepend",
            },
          ];
        },
      },
    },
  ],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/runtime-config.js": "http://127.0.0.1:8000",
      "/api/shared": "http://127.0.0.1:8002",
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rolldownOptions: {
      input: {
        owner: fileURLToPath(new URL("./index.html", import.meta.url)),
        shared: fileURLToPath(new URL("./shared.html", import.meta.url)),
      },
    },
  },
});
