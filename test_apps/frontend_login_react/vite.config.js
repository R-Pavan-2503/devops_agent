import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { vitePluginEnv } from 'vite-plugin-env'

export default defineConfig({
  plugins: [react(), vitePluginEnv()]
})