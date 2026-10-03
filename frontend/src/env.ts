/** Base URL of a remote API (the hosted backend). Empty means the API is on the same origin as the page. */
export const API_URL = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").replace(/\/$/, "");
/** True in the GitHub Pages demo build without an API: data comes from saved JSON files. */
export const IS_STATIC = import.meta.env.VITE_STATIC === "1" && !API_URL;
/** Where the app is served from (a sub-path on GitHub Pages, e.g. /NFL-Prop-Predictor/). */
export const BASE = import.meta.env.BASE_URL;
