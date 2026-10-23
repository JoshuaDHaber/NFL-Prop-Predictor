// Where each sportsbook can legally take online bets, by state (checked October 2026). Books not listed are hidden
// once the bettor's state is known, so a new book stays out until it's added here.
// DC: FanDuel and DraftKings are citywide; other books there are limited to stadium zones, so they're left out.
// Mississippi, Washington and the other retail-only states take bets in person only, so no book is legal online there.

const LEGAL: Record<string, string[]> = {
  DraftKings: ["AZ", "AR", "CO", "CT", "DC", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MO", "NH", "NJ", "NY", "NC", "OH",
    "OR", "PA", "TN", "VT", "VA", "WV", "WY"],
  FanDuel: ["AZ", "AR", "CO", "CT", "DC", "IL", "IN", "IA", "KS", "KY", "LA", "MD", "MA", "MI", "MO", "NJ", "NY", "NC", "OH", "PA", "TN",
    "VT", "VA", "WV", "WY"],
  BetMGM: ["AZ", "CO", "IL", "IN", "IA", "KS", "KY", "LA", "MD", "MA", "MI", "MO", "NV", "NJ", "NY", "NC", "OH", "PA", "PR", "TN", "VA",
    "WV", "WY"],
  Caesars: ["AZ", "CO", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MO", "NV", "NJ", "NY", "NC", "OH", "PA", "TN", "VA",
    "WV", "WY"],
  Fanatics: ["AZ", "CO", "CT", "IL", "IN", "IA", "KS", "KY", "LA", "MD", "MA", "MI", "MO", "NJ", "NY", "NC", "OH", "PA", "TN", "VT", "VA",
    "WV", "WY"],
  BetRivers: ["AZ", "CO", "DE", "IL", "IN", "IA", "LA", "MD", "MI", "NJ", "NY", "OH", "PA", "VA", "WV"],
  // offshore: not licensed in any US state
  "BetOnline.ag": [],
  BetUS: [],
  Bovada: [],
  "LowVig.ag": [],
  "MyBookie.ag": [],
};

export const isLegal = (book: string, state: string) => !!LEGAL[book]?.includes(state.trim().toUpperCase());

/** The books to show: those legal in `state`, or every book when the state is unknown or the bettor asked for all. */
export function allowedBooks(state: string, showAll: boolean): string[] | null {
  if (showAll || !state.trim()) return null;
  return Object.keys(LEGAL).filter((b) => isLegal(b, state)).sort();
}
