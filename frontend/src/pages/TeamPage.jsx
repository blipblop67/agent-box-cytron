import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import Badge from '../components/common/Badge'
import Button from '../components/common/Button'
import Modal from '../components/common/Modal'
import { Field, TextInput } from '../components/common/FormField'
import { useUserStore } from '../state/userStore'

export default function TeamPage() {
  const [members, setMembers] = useState(null)
  const [resetTarget, setResetTarget] = useState(null)
  const [removeTarget, setRemoveTarget] = useState(null)
  const [roleError, setRoleError] = useState(null)
  const currentUser = useUserStore((s) => s.user)

  async function refresh() {
    setMembers(await api.get('/users'))
  }

  useEffect(() => {
    refresh()
  }, [])

  async function toggleRole(member) {
    setRoleError(null)
    const nextRole = member.role === 'admin' ? 'member' : 'admin'
    try {
      await api.patch(`/users/${member.id}/role?role=${nextRole}`)
      refresh()
    } catch (err) {
      setRoleError(err.message)
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-8 py-8">
      <h1 className="text-lg font-semibold text-ink">Team</h1>
      <p className="mt-1 text-sm text-ink-muted">Everyone who's registered on this hub. Admins can see private knowledge bases and flows, manage hub settings, reset a teammate's password, and remove someone.</p>
      {roleError && <p className="mt-2 text-xs text-danger">{roleError}</p>}

      <div className="mt-6 overflow-hidden rounded-xl border border-line">
        {members?.map((member, i) => (
          <div
            key={member.id}
            className={`flex items-center justify-between px-4 py-3 ${i > 0 ? 'border-t border-line' : ''} bg-surface`}
          >
            <div>
              <div className="text-sm text-ink">{member.name}</div>
              <div className="font-mono text-[11px] text-ink-faint">{member.id}</div>
            </div>
            <div className="flex items-center gap-3">
              <Badge variant={member.role === 'admin' ? 'copper' : 'neutral'}>{member.role}</Badge>
              {currentUser.role === 'admin' && member.id !== currentUser.id && (
                <>
                  <button
                    onClick={() => setResetTarget(member)}
                    className="text-xs text-ink-faint underline decoration-dotted hover:text-copper"
                  >
                    Reset password
                  </button>
                  <button
                    onClick={() => toggleRole(member)}
                    className="text-xs text-ink-faint underline decoration-dotted hover:text-copper"
                  >
                    {member.role === 'admin' ? 'Remove admin' : 'Make admin'}
                  </button>
                  <button
                    onClick={() => setRemoveTarget(member)}
                    className="rounded-md p-1.5 text-ink-faint hover:bg-danger-dim hover:text-danger"
                    title={`Remove ${member.name}`}
                  >
                    <Trash2 size={13} />
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {resetTarget && <ResetPasswordModal member={resetTarget} onClose={() => setResetTarget(null)} />}
      {removeTarget && (
        <RemoveMemberModal member={removeTarget} onClose={() => setRemoveTarget(null)} onRemoved={refresh} />
      )}
    </div>
  )
}

function ResetPasswordModal({ member, onClose }) {
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.patch(`/users/${member.id}/password`, { new_password: password })
      setDone(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title={`Reset ${member.name}'s password`} onClose={onClose}>
      {done ? (
        <div className="space-y-3 text-sm">
          <p className="text-ink">
            Password reset. Tell {member.name} their new password directly - the hub has no way to
            send it for them, and they've been logged out everywhere and will need it to log back in.
          </p>
          <Button variant="secondary" onClick={onClose}>Done</Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3.5">
          <Field label="New password" hint="At least 8 characters - share it with them directly">
            <TextInput type="text" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus required />
          </Field>
          {error && <p className="text-xs text-danger">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" disabled={!password || submitting}>
              {submitting ? 'Resetting…' : 'Reset password'}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}

function RemoveMemberModal({ member, onClose, onRemoved }) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function handleConfirm() {
    setSubmitting(true)
    setError(null)
    try {
      await api.delete(`/users/${member.id}`)
      onRemoved()
      onClose()
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <Modal title={`Remove ${member.name}?`} onClose={onClose}>
      <div className="space-y-3 text-sm">
        <p className="text-ink-muted">
          This deletes their account and login. Their Gmail/Drive/Telegram connections go with it -
          nobody can reuse those. Any flows or knowledge bases they own transfer to <b>you</b> instead
          of being deleted, so the team doesn't lose shared work.
        </p>
        <p className="text-xs text-ink-faint">This can't be undone.</p>
        {error && <p className="text-xs text-danger">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="button" variant="danger" onClick={handleConfirm} disabled={submitting}>
            {submitting ? 'Removing…' : 'Remove member'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
