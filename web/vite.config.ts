import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static build: relative base so the site works from any host path (e.g. a Hugging Face Space).
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5176 },
});
