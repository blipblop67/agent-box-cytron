import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import Logo from './layout/Logo'
import Button from './common/Button'
import { useUserStore } from '../state/userStore'

export default function LoginGate() {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const error = useUserStore((s) => s.error)
  const authenticate = useUserStore((s) => s.authenticate)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim() || !password) return
    setSubmitting(true)
    try {
      await authenticate(name.trim(), password)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-line-strong bg-surface">
            <Logo size={26} />
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-ink">Agent Hub</h1>
          <p className="mt-1 text-sm text-ink-muted">Build and run AI agents on your own hardware.</p>
        </div>

        <form onSubmit={handleSubmit} className="rounded-xl border border-line-strong bg-surface p-5 shadow-xl">
          <label className="mb-1.5 block text-xs font-medium text-ink-muted">Name</label>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Priya"
            className="w-full rounded-md border border-line-strong bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-copper"
          />

          <label className="mb-1.5 mt-3 block text-xs font-medium text-ink-muted">Password</label>
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="w-full rounded-md border border-line-strong bg-bg px-3 py-2 pr-9 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-copper"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink"
              tabIndex={-1}
            >
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>

          {error && <p className="mt-2 text-xs text-danger">{error}</p>}

          <Button type="submit" variant="primary" disabled={!name.trim() || !password || submitting} className="mt-3 w-full">
            {submitting ? 'Connecting…' : 'Continue'}
          </Button>

          <p className="mt-3 text-center text-[11px] leading-relaxed text-ink-faint">
            New name? An account is created automatically - first person on this
            hub becomes its admin, everyone after that joins as a team member.
            <br />
            Existing name? Enter your password to log back in.
          </p>
        </form>
      </div>
    </div>
  )
}
