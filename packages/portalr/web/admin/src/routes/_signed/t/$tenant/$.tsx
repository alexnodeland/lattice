import { NotFound, TextLink } from "@portalr/ui";
import { createFileRoute, Link } from "@tanstack/react-router";

/** A page that isn't there, in a tenant the reader administers: in the frame (portalr ADR-0068). */
export const Route = createFileRoute("/_signed/t/$tenant/$")({
  head: ({ match }) => ({ meta: [{ title: match.context.title("Page not found") }] }),
  component: PageNotFound,
});

function PageNotFound() {
  const { tenant } = Route.useParams();
  return (
    <NotFound
      title="Page not found"
      action={<TextLink render={<Link to="/t/$tenant" params={{ tenant }} />}>Home</TextLink>}
    >
      There's nothing at this address in {tenant}.
    </NotFound>
  );
}
