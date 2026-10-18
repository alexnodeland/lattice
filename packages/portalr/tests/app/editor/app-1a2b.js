// The stand-in's code, named by a hash as a release's is: it compiles its own WebAssembly, as
// WordCraft's build does, which the editor's policy allows only from the build's own files.
export default async function start() {
  await WebAssembly.instantiateStreaming(fetch("./app-1a2b_bg.wasm"));
  document.getElementById("state").textContent = "Ready";
}
