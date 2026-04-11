// @ts-check
import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import cloudflare from "@astrojs/cloudflare";

export default defineConfig({
  adapter: cloudflare(),
  integrations: [react()],
  vite: {
    css: {
      postcss: "./postcss.config.mjs",
    },
  },
});
