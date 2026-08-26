import { create } from 'zustand'
import { api } from '../lib/api'

// Shared read-mostly data the flow editor and a couple of pages all need:
// which knowledge bases and Telegram bots exist (both visible-to-you lists,
// same shared/private model), whether Gmail/Drive/Calendar/Sheets are
// connected, whether web search/YouTube are configured hub-wide, and
// whether a Google service account is set up (lets a node "Impersonate" a
// specific Workspace address instead of using a personal connection).
// Kept as one small store rather than re-fetching in five different places.
export const useCatalogStore = create((set) => ({
  knowledgeBases: [],
  telegramBots: [],
  gmail: { connected: false },
  drive: { connected: false },
  calendar: { connected: false },
  sheets: { connected: false },
  webSearchConfigured: false,
  youtubeConfigured: false,
  serviceAccountConfigured: false,
  loaded: false,

  async load() {
    const [knowledgeBases, telegramBots, gmail, drive, calendar, sheets, settings] = await Promise.all([
      api.get('/knowledge-bases'),
      api.get('/telegram/bots'),
      api.get('/email/status'),
      api.get('/drive/status'),
      api.get('/calendar/status'),
      api.get('/sheets/status'),
      api.get('/settings'),
    ])
    set({
      knowledgeBases, telegramBots, gmail, drive, calendar, sheets,
      webSearchConfigured: settings.web_search_key_configured,
      youtubeConfigured: settings.youtube_key_configured,
      serviceAccountConfigured: settings.google_service_account_configured,
      loaded: true,
    })
  },
}))
