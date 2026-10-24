import type { Server } from "bun";
import { afterAll, beforeAll, expect, test } from "vitest";
import {
  type DiagramPlace,
  editRefusalSaid,
  imageRefusal,
  imageSize,
  readDiagramImage,
  uploadDiagramImage,
} from "./diagrams";

/** A PNG's signature and header, to its size: what is read of it before it is decoded. */
function png(width: number, height: number): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(33);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52]);
  const view = new DataView(bytes.buffer);
  view.setUint32(16, width);
  view.setUint32(20, height);
  return bytes;
}

/** A JPEG to its baseline frame: a JFIF segment, then the frame with its size. */
function jpeg(
  width: number,
  height: number,
  { marker = 0xc0, app = [] as number[] } = {},
): Uint8Array<ArrayBuffer> {
  const jfif = [0xff, 0xe0, 0, 16, ...new Array(14).fill(0)];
  const exif = app.length > 0 ? [0xff, 0xe1, (app.length + 2) >> 8, (app.length + 2) & 255] : [];
  const frame = [0xff, marker, 0, 17, 8, height >> 8, height & 255, width >> 8, width & 255];
  const bytes = [0xff, 0xd8, ...jfif, ...exif, ...frame, ...new Array(9).fill(0), 0xff, 0xd9];
  const out = new Uint8Array(bytes.length + app.length);
  // The APP segment's body goes after its header, before the frame.
  const head = 2 + jfif.length + exif.length;
  out.set(bytes.slice(0, head));
  out.set(app, head);
  out.set(bytes.slice(head), head + app.length);
  return out;
}

const PNG = png(2, 2);
const AT = "/artifactr/v1/workspaces/ws_1/diagrams/d_1/images";
const DIGEST = "a".repeat(64);
const seen: {
  method: string;
  path: string;
  type: string | null;
  tenant: string | null;
  token: string | null;
}[] = [];
let server: Server<unknown>;
let place: DiagramPlace;

beforeAll(() => {
  server = Bun.serve({
    port: 0,
    async fetch(request) {
      const url = new URL(request.url);
      seen.push({
        method: request.method,
        path: url.pathname,
        type: request.headers.get("content-type"),
        tenant: request.headers.get("x-tenant"),
        token: request.headers.get("authorization"),
      });
      if (request.method === "POST" && url.pathname === AT) {
        const body = new Uint8Array(await request.arrayBuffer());
        if (imageSize(body)?.width === 3) {
          return Response.json(
            { detail: { type: "not_an_image", message: "not a png" } },
            { status: 422 },
          );
        }
        return Response.json(
          { sha256: DIGEST, size: body.length, media_type: "image/png" },
          { status: 201 },
        );
      }
      if (url.pathname === `${AT}/${DIGEST}`) {
        return new Response(PNG, { headers: { "content-type": "image/png" } });
      }
      return Response.json({ detail: { type: "not_found", message: "no" } }, { status: 404 });
    },
  });
  place = {
    surface: `http://127.0.0.1:${server.port}/artifactr/v1/`,
    session: { token: "t0k3n" },
    tenant: "acme",
    workspace: "ws_1",
    diagram: "d_1",
  };
});

afterAll(() => server.stop());

test("an image is uploaded as its type, as the person, in the tenant, and named by its digest", async () => {
  const sent = await uploadDiagramImage(place, new Blob([PNG], { type: "image/png" }));
  expect(sent).toEqual({
    outcome: "done",
    result: { sha256: DIGEST, size: PNG.length, media_type: "image/png" },
  });
  expect(seen.at(-1)).toEqual({
    method: "POST",
    path: AT,
    type: "image/png",
    tenant: "acme",
    token: "Bearer t0k3n",
  });
});

test("what isn't a PNG or a JPEG, or is past 2 MiB, is refused before it is sent", async () => {
  const before = seen.length;
  const svg = await uploadDiagramImage(place, new Blob(["<svg/>"], { type: "image/svg+xml" }));
  const big = await uploadDiagramImage(
    place,
    new Blob([new Uint8Array(2 * 1024 * 1024 + 1)], { type: "image/png" }),
  );
  expect([svg.outcome, big.outcome]).toEqual(["refused", "refused"]);
  expect(seen.length).toBe(before);
});

test("the server's refusal is said, and a server that doesn't answer is too", async () => {
  const refused = await uploadDiagramImage(place, new Blob([png(3, 3)], { type: "image/png" }));
  expect(refused).toMatchObject({ outcome: "refused", status: 422 });
  const gone = await uploadDiagramImage(
    { ...place, surface: "http://127.0.0.1:9/artifactr/v1" },
    new Blob([PNG], { type: "image/png" }),
  );
  expect(gone).toMatchObject({ outcome: "refused", status: 0 });
});

test("an image the diagram names is read as a blob, and one it doesn't as nothing", async () => {
  const read = await readDiagramImage(place, DIGEST);
  expect(new Uint8Array(await (read as Blob).arrayBuffer())).toEqual(PNG);
  expect(await readDiagramImage(place, "b".repeat(64))).toBeNull();
  expect(await readDiagramImage({ ...place, surface: "http://127.0.0.1:9" }, DIGEST)).toBeNull();
});

test("an image's size is read from its header, as the server reads it", () => {
  expect(imageSize(png(640, 480))).toEqual({ width: 640, height: 480 });
  expect(imageSize(jpeg(800, 600))).toEqual({ width: 800, height: 600 });
  // A JPEG's fill bytes and its markers with no length are passed over.
  const filled = jpeg(5, 7);
  const padded = new Uint8Array([0xff, 0xd8, 0xff, 0xff, 0xd0, ...filled.subarray(2)]);
  expect(imageSize(padded)).toEqual({ width: 5, height: 7 });
  // A polyglot: a PNG's signature, then an SVG.
  expect(
    imageSize(new TextEncoder().encode("\u0089PNG\r\n\u001a\n<svg/>-------------")),
  ).toBeNull();
  expect(imageSize(new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 2, 0x3c, 0x73]))).toBeNull();
  expect(imageSize(new Uint8Array([0xff, 0xd8, 0xff, 0xc0, 0, 17, 8]))).toBeNull();
  expect(imageSize(new TextEncoder().encode("<svg/>"))).toBeNull();
});

test("an image of more pixels than a canvas takes is refused before it is decoded or sent", async () => {
  const before = seen.length;
  const said = (bytes: Uint8Array<ArrayBuffer>, type: string) =>
    imageRefusal(new Blob([bytes], { type }));
  expect(await said(png(20_000, 20_000), "image/png")).toMatch(/at most 8192 pixels a side/);
  expect(await said(png(9_000, 10), "image/png")).toMatch(/pixels a side/);
  expect(await said(jpeg(5_000, 5_000), "image/jpeg")).toMatch(/4096 by 4096/);
  expect(await said(png(4_096, 4_096), "image/png")).toBeNull();
  expect(await said(png(8_192, 2_048), "image/png")).toBeNull();
  expect(await said(png(8_193, 1), "image/png")).toMatch(/pixels a side/);
  expect(await said(png(0, 10), "image/png")).toBe("That image has no pixels.");
  expect(await said(jpeg(10, 0), "image/jpeg")).toBe("That image has no pixels.");
  // Progressive; and an EXIF segment of a camera's, with a thumbnail's own frame inside it.
  expect(await said(jpeg(640, 480, { marker: 0xc2 }), "image/jpeg")).toBeNull();
  const thumbnail = [...jpeg(9_000, 9_000)];
  expect(await said(jpeg(640, 480, { app: thumbnail }), "image/jpeg")).toBeNull();
  // Metadata past the first 64 KiB, before the frame: read on, as the server reads it all.
  const segment = (marker: number) => [0xff, marker, 0xea, 0x62, ...new Array(60_000).fill(0)];
  const frame = [...jpeg(640, 480)].slice(2);
  const later = new Uint8Array([0xff, 0xd8, ...segment(0xe1), ...segment(0xe2), ...frame]);
  expect(await said(later, "image/jpeg")).toBeNull();
  expect(await said(new TextEncoder().encode("<svg/>"), "image/png")).toBe("That isn't a PNG.");
  expect(await said(new TextEncoder().encode("<svg/>"), "image/jpeg")).toBe("That isn't a JPEG.");
  const bomb = await uploadDiagramImage(
    place,
    new Blob([png(20_000, 20_000)], { type: "image/png" }),
  );
  expect(bomb.outcome).toBe("refused");
  expect(seen.length).toBe(before);
});

test("a refused edit is said in the kit's words, never the server's", () => {
  expect(editRefusalSaid({ rejection: { type: "forbidden", message: "secret" } })).toBe(
    "You may not do this here.",
  );
  expect(editRefusalSaid({ rejection: { type: "odd", message: "internal" } })).not.toMatch(
    /internal/,
  );
});
