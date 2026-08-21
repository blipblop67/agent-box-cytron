import { create } from 'zustand'
import { api } from '../lib/api'

// Shared read-mostly data the flow editor and a couple of pages all need:
// which knowledge bases exist, whether Gmail/Drive/Telegram are connected,
// and whether web search is configured hub-wide. Kept as one small store
// rather than re-fetching in five different places.
export const useCatalogStore = create((set) => ({
  knowledgeBases: [],
  gmail: { connected: false },
  drive: { connected: false },
  telegram: { connected: false },
  webSearchConfigured: false,
  loaded: false,

  async load() {
    const [knowledgeBases, gmail, drive, telegram, settings] = await Promise.all([
      api.get('/knowledge-bases'),
      api.get('/email/status'),
      api.get('/drive/status'),
      api.get('/telegram/status'),
      api.get('/settings'),
    ])
    set({ knowledgeBases, gmail, drive, telegram, webSearchConfigured: settings.web_search_key_configured, loaded: true })
  },
}))
