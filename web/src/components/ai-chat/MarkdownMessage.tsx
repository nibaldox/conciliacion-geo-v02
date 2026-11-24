import { Children, cloneElement, isValidElement, useRef, type ReactNode, type ReactElement } from 'react';
import { findAgentChips, findSectionMentions } from '../../utils/agentChips';
import { AgentChip } from './AgentChip';
import { useAgentChipActions, type AgentChipActions } from './useAgentChipActions';
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
  chips?: boolean;
}

/**
 * Renders agent messages as GitHub-flavored Markdown without ever
 * producing raw HTML: no rehype-raw, no dangerouslySetInnerHTML. Links
 * are restricted to http/https/mailto/relative targets, external links
 * open in a new tab with rel="noopener noreferrer", and <img> is never
 * emitted so model content cannot trigger requests to external hosts.
 */
export function MarkdownMessage(props: MarkdownMessageProps) {
  return props.chips ? <ChippedMarkdownMessage {...props} /> : <MarkdownBody {...props} />;
}

function ChippedMarkdownMessage(props: MarkdownMessageProps) {
  const actions = useAgentChipActions();
  const context = useRef<string | null>(null);
  if (context.current === null && actions.contextSectionId !== null) context.current = actions.contextSectionId;
  return <MarkdownBody {...props} actions={{ ...actions, contextSectionId: context.current }} />;
}

function chipBlock(children: ReactNode, actions: AgentChipActions): ReactNode {
  let context = actions.contextSectionId;
  let key = 0;
  const updateContext = (text: string) => {
    for (const mention of findSectionMentions(text, actions.sections)) context = mention.section?.id ?? null;
  };
  const textContent = (child: ReactNode): string => {
    if (typeof child === 'string' || typeof child === 'number') return String(child);
    if (Array.isArray(child)) return child.map(textContent).join('');
    if (isValidElement<{ children?: ReactNode }>(child)) return textContent(child.props.children);
    return '';
  };
  const visit = (child: ReactNode): ReactNode => {
    if (typeof child === 'string') {
      const chips = findAgentChips(child, actions.sections, context);
      const result: ReactNode[] = [];
      let offset = 0;
      for (const chip of chips) {
        result.push(child.slice(offset, chip.start));
        result.push(<span key={key++} className="agent-chip-reveal"><AgentChip chip={chip} actions={actions} /></span>);
        offset = chip.end;
      }
      result.push(child.slice(offset));
      updateContext(child);
      return result;
    }
    if (Array.isArray(child)) return Children.map(child, visit);
    if (isValidElement<{ children?: ReactNode; node?: { tagName?: string } }>(child)) {
      const tag = child.props.node?.tagName ?? child.type;
      if (tag === 'strong' || tag === 'em' || tag === 'del') {
        return cloneElement(child as ReactElement<{ children?: ReactNode }>, {}, visit(child.props.children));
      }
      if (tag === 'code' || tag === 'a') updateContext(textContent(child.props.children));
    }
    return child;
  };
  return visit(children);
}

function MarkdownBody({ content, className, actions }: MarkdownMessageProps & { actions?: AgentChipActions }) {
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
              {actions ? chipBlock(children, actions) : children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="my-1 list-disc space-y-0.5 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="my-1 list-decimal space-y-0.5 pl-5">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="break-words pl-0.5">{actions ? chipBlock(children, actions) : children}</li>
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
              {actions ? chipBlock(children, actions) : children}
            </td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
