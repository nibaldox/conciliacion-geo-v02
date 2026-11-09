import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export const MAX_MARKDOWN_CHARS = 20000;

const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:']);

function sanitizeHref(url: string): string {
  let cleaned = '';
  for (const char of url) {
    const code = char.codePointAt(0) ?? 0;
    if (code > 0x20 && code !== 0x7f) cleaned += char;
  }
  if (!cleaned) return '';
  const scheme = /^[a-zA-Z][a-zA-Z\d+.-]*:/.exec(cleaned);
  if (!scheme) return cleaned;
  return SAFE_PROTOCOLS.has(scheme[0].toLowerCase()) ? cleaned : '';
}

interface MarkdownMessageProps {
  content: string;
  className?: string;
}

/**
 * Renders agent messages as GitHub-flavored Markdown without ever
 * producing raw HTML: no rehype-raw, no dangerouslySetInnerHTML. Links
 * are restricted to http/https/mailto/relative targets, external links
 * open in a new tab with rel="noopener noreferrer", and <img> is never
 * emitted so model content cannot trigger requests to external hosts.
 */
export function MarkdownMessage({ content, className }: MarkdownMessageProps) {
  if (content.length > MAX_MARKDOWN_CHARS) {
    return (
      <p className={`whitespace-pre-wrap break-words ${className ?? ''}`}>
        {content}
      </p>
    );
  }
  return (
    <div className={`min-w-0 break-words text-sm ${className ?? ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={sanitizeHref}
        components={{
          h1: ({ children }) => (
            <h1 className="mb-1 mt-2 text-base font-semibold first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-1 mt-2 text-sm font-semibold first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-1 mt-2 text-sm font-semibold first:mt-0">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="mb-1 mt-2 text-sm font-semibold first:mt-0">
              {children}
            </h4>
          ),
          p: ({ children }) => (
            <p className="my-1 whitespace-pre-wrap break-words first:mt-0 last:mb-0">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="my-1 list-disc space-y-0.5 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-1 list-decimal space-y-0.5 pl-5">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="break-words pl-0.5">{children}</li>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-1 break-words border-l-2 border-accent pl-3 text-text-secondary">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => {
            const safeHref = href ? sanitizeHref(href) : '';
            if (!safeHref) return <span>{children}</span>;
            const external = /^https?:/i.test(safeHref);
            return (
              <a
                href={safeHref}
                {...(external
                  ? { target: '_blank', rel: 'noopener noreferrer' }
                  : {})}
                className="break-words text-accent underline underline-offset-2"
              >
                {children}
              </a>
            );
          },
          img: ({ alt }) =>
            alt ? (
              <span className="break-words italic text-text-secondary">
                {alt}
              </span>
            ) : null,
          hr: () => <hr className="my-2 border-border" />,
          pre: ({ children }) => (
            <pre className="my-1 overflow-x-auto rounded-md border border-border bg-surface-muted p-2 text-xs leading-5">
              {children}
            </pre>
          ),
          code: ({ children, className: codeClassName }) =>
            codeClassName ? (
              <code className="font-mono">{children}</code>
            ) : (
              <code className="break-words rounded bg-surface-muted px-1 py-0.5 font-mono text-[0.85em]">
                {children}
              </code>
            ),
          table: ({ children }) => (
            <div className="my-1 max-w-full overflow-x-auto">
              <table className="w-full min-w-[16rem] border-collapse text-left text-xs">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-surface-muted">{children}</thead>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-surface-muted/40">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="border-b-2 border-border px-2 py-1.5 text-left text-xs font-semibold text-text-primary">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-border px-2 py-1.5 align-top">
              {children}
            </td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
