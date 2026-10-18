/** A Word document on its artifact's page, as the server answers for it, for the app's tests. */

export const AT = "/artifactr/v1/workspaces/notes";
export const FILE = `${AT}/files/doc_1`;
export const FLAGS = "/grantr/v1/tenants/acme/workspaces/notes/enabled-integrations";
const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

const manifest = (text: string, outline: string, pages: number) => ({
  name: "brief.docx",
  content: { sha256: text.repeat(64), size: 48_213, media_type: DOCX },
  fingerprint: "f".repeat(64),
  text: { sha256: text.repeat(64), size: 30, media_type: "text/plain; charset=utf-8" },
  review: null,
  outline,
  pages,
  provenance: { source: "check_in" },
});

export const REVISIONS = [
  { artifact_id: "doc_1", version: 1, kind: "word_document", data: manifest("a", "Brief", 1) },
  {
    artifact_id: "doc_1",
    version: 2,
    kind: "word_document",
    data: manifest("b", "Brief\nFees", 2),
  },
].map((revision) => ({ ...revision, archived: false, actor: { kind: "user", id: "alice" } }));

export const status = (lease: unknown, enabled = true) => ({
  artifact_id: "doc_1",
  version: 2,
  name: "brief.docx",
  media_type: DOCX,
  size: 48_213,
  outline: "Brief\nFees",
  pages: 2,
  lease,
  talk: "save",
  enabled,
  limit: 26_214_400,
});
