import path from 'path'
import fs from 'fs'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const BRANDING_FILE = path.resolve(__dirname, '../branding.json')

// Serves the repo-root branding.json at /config.json (dev) and copies it
// into the build output at <outDir>/config.json (build). Single source of
// truth. Honors --outDir so callers can build into any directory.
function brandingPlugin(): Plugin {
  let outDir = 'dist'
  return {
    name: 'dispatcher-branding',
    configResolved(config) {
      outDir = config.build.outDir
    },
    configureServer(server) {
      server.middlewares.use('/config.json', (req, res, next) => {
        if (req.method !== 'GET') return next()
        try {
          const content = fs.readFileSync(BRANDING_FILE, 'utf-8')
          res.setHeader('Content-Type', 'application/json')
          res.end(content)
        } catch (err) {
          next(err)
        }
      })
    },
    closeBundle() {
      const dest = path.isAbsolute(outDir)
        ? path.join(outDir, 'config.json')
        : path.resolve(__dirname, outDir, 'config.json')
      fs.mkdirSync(path.dirname(dest), { recursive: true })
      fs.copyFileSync(BRANDING_FILE, dest)
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), brandingPlugin()],
  /* Import alias */
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    strictPort: true,
    open: true,
  },
})
