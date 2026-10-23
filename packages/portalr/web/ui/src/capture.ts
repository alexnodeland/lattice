/** Product analytics' capture, fetched only when a person has said yes (lattice RFC-0008). */
export const loadCapture = () => import("./on-demand/analytics");
