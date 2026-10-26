import type { MouseEvent } from "react";

/** A plain left click (no Cmd, Ctrl, Shift or middle button): handle it in the page. Anything else is left to the browser, so
 *  a section or game can be opened in a new tab, long-pressed on a phone or copied as a link. */
export const plainClick = (e: MouseEvent) => e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;

/** onClick for an <a> that the app routes itself: a plain click calls go(), the rest behave as a normal link. */
export const routeClick = (go: () => void) => (e: MouseEvent) => { if (plainClick(e)) { e.preventDefault(); go(); } };
