import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { MarkdownMessage, MAX_MARKDOWN_CHARS } from '../MarkdownMessage';

describe('MarkdownMessage', () => {
  it('renders strong, em, lists, table and code', () => {
    const content = [
      '**negrita** y *énfasis*',
      '',
      '- punto uno',
      '- punto dos',
      '',
      '1. primero',
      '',
      '| clave | valor |',
      '|-------|-------|',
      '| a     | b     |',
      '',
      'usa `codigo_inline` y luego:',
      '',
      '```js',
      'const x = 1;',
      '```',
    ].join('\n');
    const { container } = render(<MarkdownMessage content={content} />);

    expect(container.querySelector('strong')?.textContent).toBe('negrita');
    expect(container.querySelector('em')?.textContent).toBe('énfasis');
    expect(container.querySelectorAll('ul > li')).toHaveLength(2);
    expect(container.querySelectorAll('ol > li')).toHaveLength(1);
    expect(container.querySelector('table')).not.toBeNull();
    expect(container.querySelector('table')?.textContent).toContain('clave');
    expect(container.textContent).toContain('codigo_inline');
    expect(container.querySelector('pre > code')).not.toBeNull();
    expect(container.textContent).toContain('const x = 1;');
  });

  it('gives https links target=_blank and a noopener rel', () => {
    const { container } = render(
      <MarkdownMessage content="[doc](https://example.com/x)" />,
    );
    const anchor = container.querySelector('a');
    expect(anchor).not.toBeNull();
    expect(anchor).toHaveAttribute('href', 'https://example.com/x');
    expect(anchor).toHaveAttribute('target', '_blank');
    expect(anchor?.getAttribute('rel')).toContain('noopener');
    expect(anchor?.getAttribute('rel')).toContain('noreferrer');
  });

  it('renders a javascript: link without any executable href', () => {
    const { container } = render(
      <MarkdownMessage content="[malo](javascript:alert(1))" />,
    );
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(container.querySelector('a[href]')).toBeNull();
    expect(container.textContent).toContain('malo');

    const entityTabbed = render(
      <MarkdownMessage content="[tramposo](java&#9;script:alert(1))" />,
    );
    expect(entityTabbed.container.querySelector('a[href]')).toBeNull();
    expect(entityTabbed.container.textContent).toContain('tramposo');
  });

  it('never renders an img element for markdown images', () => {
    const { container } = render(
      <MarkdownMessage content='![peek](http://evil/x.png)' />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('[src="http://evil/x.png"]')).toBeNull();
    expect(container.textContent).toContain('peek');
  });

  it('keeps raw HTML inert: no script element, no event handlers', () => {
    const content =
      'antes <script>alert(1)</script> medio <img src=x onerror=alert(1)> <iframe src="https://evil"></iframe> fin';
    const { container } = render(<MarkdownMessage content={content} />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.querySelector('[onerror]')).toBeNull();
    expect(container.querySelector('[onclick]')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(container.innerHTML).not.toContain('<script');
    expect(container.innerHTML).not.toContain('<img');
    expect(container.innerHTML).not.toContain('<iframe');
    expect(container.textContent).toContain('<script>alert(1)</script>');
    expect(container.textContent).toContain('onerror=alert(1)');
  });

  it('falls back to plain text above MAX_MARKDOWN_CHARS without parsing', () => {
    const content = '**b**' + 'a'.repeat(MAX_MARKDOWN_CHARS + 1);
    const { container } = render(<MarkdownMessage content={content} />);
    expect(container.querySelector('strong')).toBeNull();
    expect(container.querySelector('ul')).toBeNull();
    const paragraph = container.querySelector('p');
    expect(paragraph).not.toBeNull();
    expect(paragraph?.className).toContain('whitespace-pre-wrap');
    expect(paragraph?.className).toContain('break-words');
    expect(container.textContent).toContain('**b**');
    expect(container.textContent?.length).toBe(content.length);
  });
});
