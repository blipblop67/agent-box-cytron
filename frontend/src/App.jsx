import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import LoginGate from './components/LoginGate'
import AppShell from './components/layout/AppShell'
import FlowsPage from './pages/FlowsPage'
import FlowEditorPage from './pages/FlowEditorPage'
import KnowledgeBasesPage from './pages/KnowledgeBasesPage'
import ConnectionsPage from './pages/ConnectionsPage'
import TeamPage from './pages/TeamPage'
import SettingsPage from './pages/SettingsPage'
import AccountPage from './pages/AccountPage'
import { useUserStore } from './state/userStore'
import Logo from './components/layout/Logo'

export default function App() {
  const status = useUserStore((s) => s.status)
  const user = useUserStore((s) => s.user)
  const init = useUserStore((s) => s.init)

  useEffect(() => {
    init()
  }, [init])

  if (status === 'idle' || status === 'loading') {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-bg">
        <div className="animate-pulse opacity-60">
          <Logo size={28} />
        </div>
      </div>
    )
  }

  if (!user) {
    return <LoginGate />
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/flows" replace />} />
        <Route path="/flows" element={<FlowsPage />} />
        <Route path="/flows/:flowId" element={<FlowEditorPage />} />
        <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/flows" replace />} />
      </Route>
    </Routes>
  )
}
