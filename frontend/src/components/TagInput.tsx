import { IconX } from "@tabler/icons-react";
import { useState } from "react";
import { addTag, MAX_TAGS } from "../bets";

/** A bet's tags: chips with ×, a field that adds on Enter or comma, and the tags used before as one-tap suggestions. */
export default function TagInput({ tags, onChange, suggestions = [], id }: { tags: string[]; onChange: (t: string[]) => void; suggestions?: string[]; id?: string }) {
  const [draft, setDraft] = useState("");
  const add = (text: string) => { onChange(addTag(tags, text)); setDraft(""); };
  const unused = suggestions.filter((s) => !tags.some((t) => t.toLowerCase() === s.toLowerCase())).slice(0, 8);
  const full = tags.length >= MAX_TAGS;
  return (
    <div className="tag-input">
      <div className="tag-field">
        {tags.map((t) => (
          // the site's removable chip (Best props' active filters): the whole chip removes it
          <button type="button" className="chip-x" key={t} aria-label={`Remove tag ${t}`} onClick={() => onChange(tags.filter((x) => x !== t))}>
            {t}<IconX size={13} stroke={2} aria-hidden />
          </button>
        ))}
        {!full && (
          <input id={id} value={draft} placeholder={tags.length ? "Add another" : "e.g. SGP, Sunday"} maxLength={40} autoComplete="off"
            onChange={(e) => { const v = e.target.value; if (v.endsWith(",")) add(v.slice(0, -1)); else setDraft(v); }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) { e.preventDefault(); add(draft); }
              else if (e.key === "Backspace" && !draft && tags.length) onChange(tags.slice(0, -1));
            }}
            onBlur={() => draft.trim() && add(draft)} />
        )}
      </div>
      {unused.length > 0 && !full && (
        <div className="chips tag-suggest" aria-label="Tags you've used">
          {unused.map((s) => <button type="button" key={s} className="chip-btn" onClick={() => add(s)}>+ {s}</button>)}
        </div>
      )}
    </div>
  );
}
