import { Plain, TextLink } from "@portalr/ui";
import { createFileRoute, Link } from "@tanstack/react-router";

/** A page that isn't there, under a tenant the reader is in (portalr ADR-0068). */
export const Route = createFileRoute("/_signed/t/$tenant/$")({
  head: ({ match }) => ({ meta: [{ title: match.context.title("Page not found") }] }),
  component: () => (
    <Plain home={<Link to="/" />} title="Page not found">
      <p>There's nothing at this address.</p>
      <TextLink render={<Link to="/" />}>Start again</TextLink>
    </Plain>
  ),
});
