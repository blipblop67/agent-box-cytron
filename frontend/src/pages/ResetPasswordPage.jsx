import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Eye, EyeOff, CircleCheck } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import Logo from '../components/layout/Logo'
import Button from '../components/common/Button'

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError("Passwords don't match")
      return
    }
    setSubmitting(true)
    try {
      await api.post('/auth/reset-password', { token, new_password: password })
      setDone(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
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
          <h1 className="text-lg font-semibold tracking-tight text-ink">Reset your password</h1>
        </div>

        <div className="rounded-xl border border-line-strong bg-surface p-5 shadow-xl">
          {!token ? (
            <p className="text-sm text-danger">
              This link is missing its reset token - open it directly from the email rather than
              copying part of the URL.
            </p>
          ) : done ? (
            <div className="space-y-3 text-center">
              <CircleCheck size={28} className="mx-auto text-signal" />
              <p className="text-sm text-ink">Password changed. You can log in with it now.</p>
              <Button variant="primary" className="w-full" onClick={() => { window.location.href = '/' }}>
                Go to login
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <label className="mb-1.5 block text-xs font-medium text-ink-muted">New password</label>
              <div className="relative">
                <input
                  autoFocus
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

              <label className="mb-1.5 mt-3 block text-xs font-medium text-ink-muted">Confirm new password</label>
              <input
                type={showPassword ? 'text' : 'password'}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full rounded-md border border-line-strong bg-bg px-3 py-2 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-copper"
              />

              {error && <p className="mt-2 text-xs text-danger">{error}</p>}

              <Button type="submit" variant="primary" disabled={!password || !confirm || submitting} className="mt-3 w-full">
                {submitting ? 'Resetting…' : 'Reset password'}
              </Button>

              <p className="mt-3 text-center text-[11px] text-ink-faint">
                This link only works once and expires an hour after it was sent.
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
