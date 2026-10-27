(() => {
  const root = document.documentElement;
  const app = root.dataset.app;
  const portals = (root.dataset.portals || "").split(" ").filter(Boolean);
  const asked = new URLSearchParams(location.search).get("host");
  const portal = portals.includes(asked) ? asked : portals.length === 1 ? portals[0] : null;
  if (!portal) return;
  const methods = (root.dataset.methods || "").split(" ").filter(Boolean);
  const frame = document.querySelector("iframe");
  const own = location.origin;
  const tell = (message, transfer) => parent.postMessage(message, portal, transfer || []);
  const reply = (id, answer) => {
    try {
      tell({ type: "lattice:reply", id, ...answer });
    } catch (error) {
      tell({ type: "lattice:reply", id, error: String(error) });
    }
  };
  const buffer = (bytes) =>
    bytes instanceof ArrayBuffer
      ? bytes
      : ArrayBuffer.isView(bytes)
        ? new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength).slice().buffer
        : null;
  const fromPortal = (data) => {
    const bytes = buffer(data.bytes);
    if (data.type === "lattice:open" && typeof data.name === "string" && bytes) {
      frame.contentWindow.postMessage({ type: `${app}:open`, name: data.name, bytes }, own, [
        bytes,
      ]);
    } else if (data.type === "lattice:call") {
      // The method called is the allowed name itself, found in the list, never the message's.
      const method = methods.find((name) => name === data.method);
      if (method === undefined) return;
      const args = Array.isArray(data.args) ? data.args : [];
      Promise.resolve()
        .then(() => frame.contentWindow[app][method](...args))
        .then(
          (result) => reply(data.id, { result }),
          (error) => reply(data.id, { error: String(error) }),
        );
    }
  };
  const fromBuild = (data) => {
    const bytes = buffer(data.bytes);
    if (data.type === `${app}:ready`) {
      tell({ type: "lattice:ready", version: String(data.version || "") });
    } else if (data.type === `${app}:dirty`) {
      tell({ type: "lattice:dirty", dirty: data.dirty === true });
    } else if (data.type === `${app}:failed`) {
      tell({ type: "lattice:failed", error: String(data.error || "") });
    } else if (data.type === `${app}:save` && typeof data.name === "string" && bytes) {
      tell({ type: "lattice:save", name: data.name, bytes }, [bytes]);
    }
  };
  addEventListener("message", (event) => {
    const data = event.data;
    if (typeof data !== "object" || data === null || typeof data.type !== "string") return;
    if (event.source === parent && event.origin === portal) fromPortal(data);
    else if (event.source === frame.contentWindow && event.origin === own) fromBuild(data);
  });
  if (root.dataset.surface === "global") {
    const started = Date.now();
    const ready = setInterval(() => {
      const api = frame.contentWindow?.[app];
      if (api || Date.now() - started > 60000) {
        clearInterval(ready);
        const failed = { type: "lattice:failed", error: `the build has no ${app} API` };
        tell(api ? { type: "lattice:ready", version: "" } : failed);
      }
    }, 100);
  }
  frame.src = root.dataset.surface === "parent" ? "/?host=parent" : "/";
})();
