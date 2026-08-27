import { create } from 'zustand'
import { api } from '../lib/api'

// Shared read-mostly data the flow editor and a couple of pages all need:
// which knowledge bases and Telegram bots exist (both visible-to-you lists,
// same shared/private model), whether web search/YouTube are configured
// hub-wide, and whether a Google service account is set up (lets a node
// "Impersonate" a specific Workspace address, or act as the service
// account itself if left blank - see SettingsPage's Google card). There's
// no per-person "connected" state for Google services anymore - a single
// hub-wide service account replaced the old per-user OAuth model entirely.
// Kept as one small store rather than re-fetching in four different places.
export const useCatalogStore = create((set) => ({
  knowledgeBases: [],
  telegramBots: [],
  webSearchConfigured: false,
  youtubeConfigured: false,
  serviceAccountConfigured: false,
  serviceAccountEmail: '',
  loaded: false,

  async load() {
    const [knowledgeBases, telegramBots, settings] = await Promise.all([
      api.get('/knowledge-bases'),
      api.get('/telegram/bots'),
      api.get('/settings'),
    ])
    set({
      knowledgeBases, telegramBots,
      webSearchConfigured: settings.web_search_key_configured,
      youtubeConfigured: settings.youtube_key_configured,
      serviceAccountConfigured: settings.google_service_account_configured,
      serviceAccountEmail: settings.google_service_account_email,
      loaded: true,
    })
  },
}))
