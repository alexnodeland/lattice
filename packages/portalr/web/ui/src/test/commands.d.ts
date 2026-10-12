/** The browser commands vitest.config.ts adds. */
declare module "vitest/browser" {
  interface BrowserCommands {
    reduceMotion: (reduce: boolean) => Promise<void>;
  }
}

export {};
