import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Workflow, Database, Plug, Users, Settings, UserCircle, LogOut } from 'lucide-react'
import Logo from './Logo'
import Badge from '../common/Badge'
import { api } from '../../lib/api'
import { useUserStore } from '../../state/userStore'

const NAV = [
  { to: '/flows', label: 'Flows', icon: Workflow },
  { to: '/knowledge-bases', label: 'Knowledge bases', icon: Database },
  { to: '/connections', label: 'Connections', icon: Plug },
  { to: '/team', label: 'Team', icon: Users },
  { to: '/account', label: 'Account', icon: UserCircle },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  const user = useUserStore((s) => s.user)
  const logout = useUserStore((s) => s.logout)
  const [hubName, setHubName] = useState('')

  useEffect(() => {
    api.get('/settings').then((s) => {
      setHubName(s.hub_name || '')
      document.title = s.hub_name ? `${s.hub_name} — Agent Hub` : 'Agent Hub'
    })
  }, [])

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r border-line bg-surface">
      <div className="flex items-center gap-2 px-4 py-4">
        <Logo />
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold tracking-tight text-ink">Agent Hub</div>
          <div className="truncate font-mono text-[10px] text-ink-faint">{hubName || 'local hub'}</div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-2.5 py-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-surface-raised text-ink'
                  : 'text-ink-muted hover:bg-surface-raised hover:text-ink'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={16} strokeWidth={1.85} className={isActive ? 'text-copper' : ''} />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {user && (
        <div className="border-t border-line px-3 py-3">
          <div className="flex items-center justify-between gap-2 rounded-md px-1.5 py-1.5">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-ink">{user.name}</div>
              <Badge variant={user.role === 'admin' ? 'copper' : 'neutral'} className="mt-1">
                {user.role}
              </Badge>
            </div>
            <button
              onClick={logout}
              className="shrink-0 rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-raised hover:text-danger"
              title="Log out"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      )}
    </aside>
  )
}
