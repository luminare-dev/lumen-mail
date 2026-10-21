// Texts of the command palette, all through Roundcube's own label mechanism.
//
// The skin's footer wrapper registers every label the palette uses with <roundcube:add_label>:
// Roundcube's core labels (mail, compose, inbox ...) in the user's language, and the skin's own
// labels from skins/lumen/localization/<lang>.inc under the "lumen." prefix (Roundcube reads
// en_US.inc first and the user's language on top, so every key always has a text). The bundle
// carries no copy of the texts. The build guarantees they exist: tests/test_palette_consistency.py
// keeps OWN_KEYS and CORE_KEYS equal to the wrapper's labels and the localization files, and the
// generator's drift check stops if the installed Roundcube lacks one of the core labels.

import type { Rcmail } from "./types";

/** The skin's own labels (localization/*.inc), without the "lumen." prefix. */
export const OWN_KEYS = [
  "palette_open",
  "palette_trigger",
  "palette_title",
  "palette_placeholder",
  "palette_empty",
  "palette_results",
  "palette_hint",
  "palette_current",
  "palette_group_tasks",
  "palette_group_folders",
  "palette_group_settings",
  "palette_group_actions",
] as const;

/** Roundcube core labels the palette uses. */
export const CORE_KEYS = [
  "mail",
  "contacts",
  "settings",
  "compose",
  "checkmail",
  "search",
  "inbox",
  "about",
  "logout",
  "darkmode",
  "lightmode",
  "preferences",
  "folders",
  "identities",
  "responses",
  "close",
] as const;

export type OwnKey = (typeof OWN_KEYS)[number];
export type CoreKey = (typeof CORE_KEYS)[number];
export type Translate = (key: OwnKey | CoreKey, vars?: Record<string, string | number>) => string;

const OWN = new Set<string>(OWN_KEYS);

export function translator(rc: Pick<Rcmail, "get_label"> | null | undefined): Translate {
  return (key, vars) => {
    const name = OWN.has(key) ? `lumen.${key}` : key;
    let text = "";
    try {
      text = String(rc?.get_label?.(name) ?? "");
    } catch {
      text = "";
    }
    text ||= name;
    if (vars) for (const [k, v] of Object.entries(vars)) text = text.split(`$${k}`).join(String(v));
    return text;
  };
}
