// @ts-check
import { defineConfig } from "astro/config";
import react from "@astrojs/react";

export default defineConfig({
  output: "static",
  integrations: [react()],
  vite: {
    css: {
      postcss: "./postcss.config.mjs",
    },
  },
});
