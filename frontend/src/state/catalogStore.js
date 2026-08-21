import { create } from 'zustand'
import { api } from '../lib/api'

// Shared read-mostly data the flow editor and a couple of pages all need:
// which knowledge bases exist, and whether Gmail/Drive are connected. Kept
// as one small store rather than re-fetching in five different places.
export const useCatalogStore = create((set) => ({
  knowledgeBases: [],
  gmail: { connected: false },
  drive: { connected: false },
  telegram: { connected: false },
  loaded: false,

  async load() {
    const [knowledgeBases, gmail, drive, telegram] = await Promise.all([
      api.get('/knowledge-bases'),
      api.get('/email/status'),
      api.get('/drive/status'),
      api.get('/telegram/status'),
    ])
    set({ knowledgeBases, gmail, drive, telegram, loaded: true })
  },
}))
