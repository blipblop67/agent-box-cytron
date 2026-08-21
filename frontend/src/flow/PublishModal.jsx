import { useState } from 'react'
import { Copy, Check, Rocket, Unplug } from 'lucide-react'
import { api } from '../lib/api'
import Modal from '../components/common/Modal'
import Button from '../components/common/Button'
import { useFlowEditorStore } from '../state/flowEditorStore'

export default function PublishModal({ onClose }) {
  const flowId = useFlowEditorStore((s) => s.flowId)
  const published = useFlowEditorStore((s) => s.published)
  const setFlowMeta = useFlowEditorStore((s) => s.setFlowMeta)
  const [apiKey, setApiKey] = useState(null)
  const [runUrl, setRunUrl] = useState(null)
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handlePublish() {
    setBusy(true)
    try {
      const result = await api.post(`/flows/${flowId}/publish`, {})
      setApiKey(result.api_key)
      setRunUrl(result.run_url)
      setFlowMeta({ published: true })
    } finally {
      setBusy(false)
    }
  }

  async function handleUnpublish() {
    setBusy(true)
    try {
      await api.delete(`/flows/${flowId}/publish`)
      setFlowMeta({ published: false })
      setApiKey(null)
      onClose()
    } finally {
      setBusy(false)
    }
  }

  async function handleCopy(text) {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const curlExample = apiKey && runUrl
    ? `curl -X POST ${origin}${runUrl} \\\n  -H "X-API-Key: ${apiKey}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"input": "hello"}'`
    : null

  return (
    <Modal title="Publish as an API" onClose={onClose} width="max-w-lg">
      <div className="space-y-4">
        <p className="text-sm text-ink-muted">
          Lets this flow be called from outside the hub entirely - a website, a script, another
          app - using an API key instead of logging in. No session, no cookies, just the key below.
        </p>

        {apiKey ? (
          <>
            <div className="rounded-md border border-copper/30 bg-copper-dim p-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-copper-bright">
                Your API key - shown once, save it now
              </p>
              <div className="mt-1.5 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-surface px-2 py-1.5 font-mono text-xs text-ink">{apiKey}</code>
                <button onClick={() => handleCopy(apiKey)} className="shrink-0 rounded p-1.5 text-ink-faint hover:bg-surface hover:text-copper" title="Copy">
                  {copied ? <Check size={14} className="text-signal" /> : <Copy size={14} />}
                </button>
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-ink-muted">Example</p>
              <pre className="mt-1.5 overflow-x-auto rounded-md border border-line-strong bg-bg p-3 font-mono text-[11px] leading-relaxed text-ink-muted">{curlExample}</pre>
            </div>
            <p className="text-xs text-ink-faint">
              Publishing again generates a new key and immediately invalidates this one.
            </p>
          </>
        ) : published ? (
          <p className="rounded-md border border-signal/30 bg-signal-dim px-3 py-2 text-xs text-signal">
            This flow is already published. Publish again to see a fresh key (this invalidates the
            current one), or unpublish to take it offline.
          </p>
        ) : (
          <p className="text-xs text-ink-faint">Not published yet - nobody outside the hub can call this flow.</p>
        )}

        <div className="flex items-center justify-between gap-2 border-t border-line pt-4">
          {published && (
            <Button variant="ghost" onClick={handleUnpublish} disabled={busy}>
              <Unplug size={13} /> Unpublish
            </Button>
          )}
          <div className="ml-auto flex gap-2">
            <Button variant="ghost" onClick={onClose}>Close</Button>
            <Button variant="primary" onClick={handlePublish} disabled={busy}>
              <Rocket size={13} /> {published ? 'Generate new key' : 'Publish'}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
