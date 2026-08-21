import { LogIn, LogOut, Sparkles, BookOpen, Mail, HardDrive, Calculator, Send, Globe } from 'lucide-react'

// Every node type's display metadata in one place - the palette, the node
// card, and the config panel all read from this rather than each hardcoding
// icons/labels/categories separately.
export const NODE_REGISTRY = {
  input: { label: 'Input', icon: LogIn, category: 'io', description: 'Where a run starts' },
  llm: { label: 'LLM', icon: Sparkles, category: 'model', description: 'Ask a language model' },
  knowledge_base: { label: 'Knowledge base', icon: BookOpen, category: 'tool', description: 'Search your documents' },
  web_search: { label: 'Web search', icon: Globe, category: 'tool', description: 'Search the live web' },
  email: { label: 'Email', icon: Mail, category: 'tool', description: 'Send or search Gmail' },
  drive: { label: 'Drive', icon: HardDrive, category: 'tool', description: 'List, read, or create files' },
  telegram: { label: 'Telegram', icon: Send, category: 'tool', description: 'Send or read a Telegram chat' },
  calculator: { label: 'Calculator', icon: Calculator, category: 'tool', description: 'Evaluate a math expression' },
  output: { label: 'Output', icon: LogOut, category: 'io', description: 'The final result of the run' },
}

export const PALETTE_ORDER = ['input', 'llm', 'knowledge_base', 'web_search', 'email', 'drive', 'telegram', 'calculator', 'output']

// Full literal class names (not built via string interpolation) so Tailwind's
// scanner can find them - see FlowNode.jsx for how these get used.
export const CATEGORY_CLASSES = {
  io: { bar: 'bg-ink-faint', icon: 'text-ink-muted' },
  model: { bar: 'bg-copper', icon: 'text-copper' },
  tool: { bar: 'bg-signal', icon: 'text-signal' },
}

export const NODE_DEFAULTS = {
  input: {},
  llm: { provider: '', model: '', system_prompt: '' },
  knowledge_base: { kb_id: '', top_k: 5 },
  web_search: { query: '', max_results: 5 },
  email: { action: 'send', to: '', subject: '', body: '', query: '', max_results: 5 },
  drive: { action: 'list', search: '', file_id: '', file_name: '', name: '', content: '', mime_type: 'text/plain' },
  telegram: { action: 'send', message: '', max_results: 10 },
  calculator: { expression: '' },
  output: {},
}
