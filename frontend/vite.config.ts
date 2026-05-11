import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'

// Optional HTTPS for LAN dev — required by iOS Safari AR Quick Look.
// Generate certs once with `mkcert localhost 127.0.0.1 <laptop-LAN-IP>`
// from inside ./.cert/ and they get picked up automatically. Without
// the .cert/ folder we fall back to plain HTTP for local desktop work.
function loadHttps() {
  const certDir = path.resolve(__dirname, '.cert')
  if (!fs.existsSync(certDir)) return undefined
  const files = fs.readdirSync(certDir)
  const keyFile = files.find((f) => f.endsWith('-key.pem'))
  const certFile = files.find((f) => f.endsWith('.pem') && !f.endsWith('-key.pem'))
  if (!keyFile || !certFile) return undefined
  return {
    key: fs.readFileSync(path.join(certDir, keyFile)),
    cert: fs.readFileSync(path.join(certDir, certFile)),
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    https: loadHttps(),
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      // MinIO objects (images + GLB models) — proxied so phone clients on the
      // LAN can reach them through the vite host without exposing port 9000.
      '/minio': {
        target: 'http://minio:9000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/minio/, ''),
      },
    },
  },
})
