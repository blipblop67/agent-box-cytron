import { create } from 'zustand'
import { api } from '../lib/api'

// Shared read-mostly data the flow editor and a couple of pages all need:
// which knowledge bases and Telegram bots exist (both visible-to-you lists,
// same shared/private model), whether web search/YouTube are configured
// hub-wide, whether a Google service account is set up (lets a node
// "Impersonate" a specific Workspace address, or act as the service
// account itself if left blank - see SettingsPage's Google card), whether
// this hub's own Google OAuth client is set up (Path B - lets a node act
// as the person building the flow instead, via their own personal
// connection - see ConnectionsPage), and that person's own connection
// status for each of the four Google services, so a node's auth_mode
// selector can show "you're connected" without a separate fetch per node.
// Kept as one small store rather than re-fetching in four different places.
export const useCatalogStore = create((set) => ({
  knowledgeBases: [],
  telegramBots: [],
  webSearchConfigured: false,
  youtubeConfigured: false,
  serviceAccountConfigured: false,
  serviceAccountEmail: '',
  googleOAuthConfigured: false,
  googleConnections: { email: null, drive: null, calendar: null, sheets: null },
  loaded: false,

  async load() {
    const [knowledgeBases, telegramBots, settings] = await Promise.all([
      api.get('/knowledge-bases'),
      api.get('/telegram/bots'),
      api.get('/settings'),
    ])
    const googleOAuthConfigured = settings.google_oauth_client_secret_configured
    const googleConnections = googleOAuthConfigured
      ? Object.fromEntries(
          await Promise.all(
            ['email', 'drive', 'calendar', 'sheets'].map(async (key) => [key, await api.get(`/${key}/status`)]),
          ),
        )
      : { email: null, drive: null, calendar: null, sheets: null }
    set({
      knowledgeBases, telegramBots,
      webSearchConfigured: settings.web_search_key_configured,
      youtubeConfigured: settings.youtube_key_configured,
      serviceAccountConfigured: settings.google_service_account_configured,
      serviceAccountEmail: settings.google_service_account_email,
      googleOAuthConfigured,
      googleConnections,
      loaded: true,
    })
  },
}))
