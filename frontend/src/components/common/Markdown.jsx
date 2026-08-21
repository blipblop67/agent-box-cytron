import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'

// Renders LLM output properly instead of showing raw markdown syntax -
// **bold** should look bold, $x^2$ should look like actual math, code
// blocks should be monospaced. Used anywhere a model's response is shown:
// Chat messages and the Run panel's output. remark-math + rehype-katex
// handles $inline$ and $$block$$ LaTeX; remark-gfm adds tables, strikethrough,
// and task lists on top of standard markdown.
export default function Markdown({ children, className = '' }) {
  return (
    <div className={`markdown-body ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          p: ({ children }) => <p className="mb-2.5 leading-relaxed last:mb-0">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          h1: ({ children }) => <h1 className="mb-2 mt-3 text-base font-semibold text-ink first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-3 text-sm font-semibold text-ink first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-1.5 mt-2.5 text-sm font-semibold text-ink first:mt-0">{children}</h3>,
          ul: ({ children }) => <ul className="mb-2.5 ml-4 list-disc space-y-1 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2.5 ml-4 list-decimal space-y-1 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-copper underline decoration-copper/40 hover:text-copper-bright">
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="mb-2.5 border-l-2 border-line-strong pl-3 italic text-ink-muted last:mb-0">{children}</blockquote>
          ),
          hr: () => <hr className="my-3 border-line" />,
          code: ({ children, ...props }) => (
            <code className="rounded bg-surface-raised px-1.5 py-0.5 font-mono text-[0.85em] text-copper-bright" {...props}>
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="mb-2.5 overflow-x-auto rounded-md border border-line-strong bg-bg p-3 font-mono text-[0.85em] leading-relaxed text-ink [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-ink last:mb-0">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="mb-2.5 overflow-x-auto last:mb-0">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="border-b border-line-strong">{children}</thead>,
          th: ({ children }) => <th className="px-2 py-1.5 text-left font-medium text-ink">{children}</th>,
          td: ({ children }) => <td className="border-t border-line px-2 py-1.5 text-ink-muted">{children}</td>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
