/** The browser commands vitest.config.ts adds. */
declare module "vitest/browser" {
  interface BrowserCommands {
    forcedColors: (active: boolean) => Promise<void>;
    pointerAway: () => Promise<void>;
    reduceMotion: (reduce: boolean) => Promise<void>;
  }
}

export {};
