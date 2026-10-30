/** The browser commands vitest.config.ts adds. */
declare module "vitest/browser" {
  interface BrowserCommands {
    /** Ask for forced colours, as a high-contrast mode does, or stop asking. */
    forcedColors: (active: boolean) => Promise<void>;
  }
}

export {};
