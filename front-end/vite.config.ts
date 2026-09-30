import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // O5: manual chunk splitting to keep the main chunk small
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Leaflet and its dependencies → separate chunk
          if (id.includes('leaflet') || id.includes('react-leaflet')) {
            return 'leaflet';
          }
          // Recharts → separate chunk
          if (id.includes('recharts') || id.includes('d3-')) {
            return 'recharts';
          }
          // i18n → separate chunk
          if (id.includes('i18next') || id.includes('react-i18next')) {
            return 'i18n';
          }
          // React core + router + query → shared vendor chunk
          if (
            id.includes('node_modules/react/') ||
            id.includes('node_modules/react-dom/') ||
            id.includes('node_modules/react-router') ||
            id.includes('node_modules/@tanstack/react-query')
          ) {
            return 'vendor-react';
          }
          // UI components (radix, shadcn) → shared ui chunk
          if (id.includes('node_modules/@radix-ui') || id.includes('node_modules/class-variance')) {
            return 'vendor-ui';
          }
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
});
