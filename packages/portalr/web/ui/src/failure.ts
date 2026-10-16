/** What a failure says, as every screen shows it: its message as a sentence of its own. */

/** A failure's message, its first letter a capital, for where it starts a sentence. */
export const failureSaid = (error: unknown): string => {
  const said = error instanceof Error ? error.message : String(error);
  return said.charAt(0).toUpperCase() + said.slice(1);
};
