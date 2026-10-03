/** True in the GitHub Pages build: data comes from saved JSON files instead of the API. */
export const IS_STATIC = import.meta.env.VITE_STATIC === "1";
/** Where the app is served from (a sub-path on GitHub Pages, e.g. /NFL-Prop-Predictor/). */
export const BASE = import.meta.env.BASE_URL;
