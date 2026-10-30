import { defineConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

// Собирает один самодостаточный index.html (JS + WASM inline),
// который мобилка кладёт в ассеты и открывает в WebView офлайн.
export default defineConfig({
  plugins: [viteSingleFile()],
  build: {
    outDir: 'dist',
  },
});
