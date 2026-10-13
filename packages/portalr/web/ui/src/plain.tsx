import { useRender } from "@base-ui/react/use-render";
import type { ReactElement, ReactNode } from "react";
import { Lockup, type Ui } from "./marks";
import { PageHeader } from "./page-header";

/**
 * A plain page, outside the frame: the lockup as a link home, and the account where someone is
 * signed in, above one column of its title and what it holds. For signing in's neighbours:
 * choosing a tenant or a workspace, and what went wrong.
 */
export function Plain({
  ui = "app",
  home,
  title,
  account,
  children,
}: {
  /** Whose lockup it shows: `app`'s or `admin`'s. */
  ui?: Ui;
  /** The link home, such as the router's, that the lockup renders as. */
  home: ReactElement;
  title: string;
  account?: ReactNode;
  children?: ReactNode;
}) {
  const link = useRender({
    defaultTagName: "a",
    render: home,
    props: {
      "aria-label": ui === "admin" ? "portalr admin" : "portalr",
      className:
        "inline-flex rounded-md outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus",
      children: <Lockup ui={ui} />,
    },
  });
  return (
    <div className="min-h-dvh">
      <header className="flex items-center justify-between gap-4 border-line border-b bg-surface px-4 py-2 sm:px-6">
        {link}
        {account}
      </header>
      <main
        id="main"
        className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8 sm:px-6 lg:py-12"
      >
        <PageHeader title={title} />
        {children}
      </main>
    </div>
  );
}
