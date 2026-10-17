/**
 * Markdown to render in tests, the screenshots and the CSP harness: every element an agent writes,
 * and what a hostile message holds.
 */

/** Every element `Markdown` draws, once. */
export const GALLERY = `# The launch plan

A paragraph with **bold**, *italic*, ~~struck~~, \`inline code\`, a [link](https://example.com) and a footnote.[^why]

## Steps

1. Branch from \`main\`.
2. Open a pull request.
   - [x] Tests pass
   - [ ] Docs updated

| Package | Owner | Status | A rather long column heading that makes the table wider than a phone |
|---|---|---|---|
| portalr | Alex | Shipped | Each cell holds a few words |
| artifactr | Alex | In review | And this one, a few more |

> A plain quote, as a reader would write one.

> [!NOTE]
> The queue merges every green pull request.

> [!TIP]
> Group related work into one pull request.

> [!IMPORTANT]
> Decisions go in an ADR.

> [!WARNING]
> A failed batch is bisected.

> [!CAUTION]
> Never loosen the Content-Security-Policy.

\`\`\`ts
export function greet(name: string): string {
  return \`Hello, \${name}, and a line long enough that it scrolls sideways on a narrow screen\`;
}
\`\`\`

\`\`\`
plain text, in no language
\`\`\`

\`\`\`mermaid
flowchart LR
  Branch --> Queue --> Main
\`\`\`

---

[^why]: Because a model cites its sources.
`;

/** What a message may hold that must never run, load or link: each must show as text, or not at all. */
export const HOSTILE = [
  "<script>alert(1)</script>",
  "<img src=x onerror=alert(1)>",
  '<a href="javascript:alert(1)">html link</a>',
  "[md link](javascript:alert(1))",
  "![pixel](https://tracker.example/pixel.gif)",
  '<style>body{display:none}</style><div style="color:red">styled</div>',
  "<iframe src=https://example.com></iframe>",
  "> [!NOTE]\n> <img src=x onerror=alert(1)>",
  '```mermaid\nflowchart LR\n  A["<img src=x onerror=alert(1)>"] --> B\n  click A "javascript:alert(1)"\n```',
  "[^x]\n\n[^x]: <script>alert(1)</script>",
  // A language named for what every object has, which a lookup by name must not find.
  "```constructor\nx\n```\n\n```__proto__\ny\n```\n\n```toString\nz\n```",
] as const;
