/**
 * The native files' add-on (portalr ADR-0048, ADR-0044): a native file's section on its page, its
 * view in a thread, its proposals and what a revision changed in its words, with the check-out,
 * the editor's frame and the page and sheet views they hold. A chunk of its own, loaded the first
 * time a page draws a native file's part; `files` places each part.
 */

export { NativeFile, TextChanges } from "../native-file";
export { NativeInline } from "../native-inline";
export { NativeProposal } from "../native-proposal";
