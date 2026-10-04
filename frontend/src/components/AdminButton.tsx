import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { setToken, useToken } from "../auth";

/** Unlocks refreshes and alternate-line fetches on a hosted API with the owner's password. Everyone else gets the read-only app. */
export default function AdminButton({ canWrite }: { canWrite: boolean }) {
  const qc = useQueryClient();
  const token = useToken();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");

  const save = () => { setToken(draft.trim()); setDraft(""); setOpen(false); qc.invalidateQueries(); };
  const signOut = () => { setToken(""); setOpen(false); qc.invalidateQueries(); };

  return (
    <div className="admin">
      <button className="link" onClick={() => setOpen(!open)} aria-expanded={open}>
        {canWrite ? "Admin ✓" : token ? "Admin (wrong password)" : "Admin"}
      </button>
      {open && (
        <div className="admin-pop">
          {canWrite ? (
            <>
              <p className="mut">Signed in: refreshes and alternate-line fetches are unlocked in this browser.</p>
              <button className="primary" onClick={signOut}>Sign out</button>
            </>
          ) : (
            <>
              <p className="mut">Enter the admin password to refresh data on this site. Visitors without it can browse but can't spend API credits. Repeated wrong guesses are slowed down.</p>
              <input type="password" value={draft} placeholder="Admin password" autoComplete="off"
                onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && draft && save()} />
              <button className="primary" disabled={!draft} onClick={save}>Unlock</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
