import { create } from 'zustand'
import { api } from '../lib/api'

// Shared read-mostly data the flow editor and a couple of pages all need:
// which knowledge bases and Telegram bots exist (both visible-to-you lists,
// same shared/private model), whether Gmail/Drive/Calendar are connected,
// and whether web search / YouTube are configured hub-wide. Kept as one
// small store rather than re-fetching in five different places.
export const useCatalogStore = create((set) => ({
  knowledgeBases: [],
  telegramBots: [],
  gmail: { connected: false },
  drive: { connected: false },
  calendar: { connected: false },
  webSearchConfigured: false,
  youtubeConfigured: false,
  loaded: false,

  async load() {
    const [knowledgeBases, telegramBots, gmail, drive, calendar, settings] = await Promise.all([
      api.get('/knowledge-bases'),
      api.get('/telegram/bots'),
      api.get('/email/status'),
      api.get('/drive/status'),
      api.get('/calendar/status'),
      api.get('/settings'),
    ])
    set({
      knowledgeBases, telegramBots, gmail, drive, calendar,
      webSearchConfigured: settings.web_search_key_configured,
      youtubeConfigured: settings.youtube_key_configured,
      loaded: true,
    })
  },
}))
