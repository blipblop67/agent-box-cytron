import { useState } from 'react'
import { Eye, EyeOff, CircleCheck } from 'lucide-react'
import Logo from './layout/Logo'
import Button from './common/Button'
import { api, ApiError } from '../lib/api'
import { useUserStore } from '../state/userStore'

export default function LoginGate() {
  const [mode, setMode] = useState('login') // 'login' | 'forgot'
  return mode === 'forgot' ? (
    <ForgotPasswordForm onBack={() => setMode('login')} />
  ) : (
    <LoginForm onForgotPassword={() => setMode('forgot')} />
  )
}

function LoginForm({ onForgotPassword }) {
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
    <AuthShell title="Agent Hub" subtitle="Build and run AI agents on your own hardware.">
      <form onSubmit={handleSubmit}>
        <label className="mb-1.5 block text-xs font-medium text-ink-muted">Name</label>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Priya"
          className="w-full rounded-md border border-line-strong bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-copper"
        />

        <div className="mb-1.5 mt-3 flex items-center justify-between">
          <label className="block text-xs font-medium text-ink-muted">Password</label>
          <button type="button" onClick={onForgotPassword} className="text-[11px] text-copper hover:underline">
            Forgot password?
          </button>
        </div>
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
    </AuthShell>
  )
}

function ForgotPasswordForm({ onBack }) {
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      // the backend always returns this same generic response whether or
      // not the account/email exists - nothing to branch on here, an
      // actual thrown error means the request itself failed, not that the
      // account doesn't exist
      await api.post('/auth/forgot-password', { name: name.trim() })
      setSent(true)
    } catch (err) {
      setError('Something went wrong sending that - check your connection and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell title="Reset your password" subtitle="Enter your name and we'll email a reset link, if that account has one set up.">
      {sent ? (
        <div className="space-y-3 text-center">
          <CircleCheck size={28} className="mx-auto text-signal" />
          <p className="text-sm text-ink">
            If "{name.trim()}" has a recovery email set up, a reset link was just sent to it.
          </p>
          <p className="text-xs text-ink-faint">
            No recovery email set, or no admin has configured outgoing email yet? Ask a hub admin
            to reset your password from the Team page, or - if you're the only admin - see
            <code className="mx-1 rounded bg-surface-raised px-1 py-0.5">reset_password.py</code>
            in the project's backend folder.
          </p>
          <Button variant="secondary" className="w-full" onClick={onBack}>Back to login</Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          <label className="mb-1.5 block text-xs font-medium text-ink-muted">Name</label>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Priya"
            className="w-full rounded-md border border-line-strong bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-copper"
          />
          <Button type="submit" variant="primary" disabled={!name.trim() || submitting} className="mt-3 w-full">
            {submitting ? 'Sending…' : 'Send reset link'}
          </Button>
          {error && <p className="mt-2 text-xs text-danger">{error}</p>}
          <button type="button" onClick={onBack} className="mt-3 w-full text-center text-xs text-ink-faint hover:text-ink">
            Back to login
          </button>
        </form>
      )}
    </AuthShell>
  )
}

function AuthShell({ title, subtitle, children }) {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-line-strong bg-surface">
            <Logo size={26} />
          </div>
          <h1 className="text-lg font-semibold tracking-tight text-ink">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
        </div>
        <div className="rounded-xl border border-line-strong bg-surface p-5 shadow-xl">{children}</div>
      </div>
    </div>
  )
}
