// A mocked rcmail for the gallery: just the parts of Roundcube's client API the palette uses.
// Commands are not run; each one is reported to the page (a "lumen-gallery-command" event).
// The labels: the skin's own from skin/localization/*.inc (read at build time), and stand-ins
// for Roundcube's core labels written for the gallery.

import data from "virtual:lumen-gallery";
import type { Mailbox, Rcmail } from "../../palette/src/types";

export type Lang = "en" | "de";

const CORE: Record<Lang, Record<string, string>> = {
  en: {
    mail: "Mail", contacts: "Contacts", settings: "Settings", compose: "Compose", checkmail: "Check for new mail",
    search: "Search", inbox: "Inbox", about: "About", logout: "Log out", darkmode: "Dark mode", lightmode: "Light mode",
    preferences: "Preferences", folders: "Folders", identities: "Identities", responses: "Responses", close: "Close",
  },
  de: {
    mail: "E-Mail", contacts: "Kontakte", settings: "Einstellungen", compose: "Verfassen",
    checkmail: "Auf neue E-Mails prüfen", search: "Suchen", inbox: "Posteingang", about: "Über", logout: "Abmelden",
    darkmode: "Dunkler Modus", lightmode: "Heller Modus", preferences: "Präferenzen", folders: "Ordner",
    identities: "Identitäten", responses: "Antwortvorlagen", close: "Schließen",
  },
};

const FOLDERS: [string, string, string][] = [
  // id, English name, German name
  ["INBOX", "Inbox", "Posteingang"],
  ["Drafts", "Drafts", "Entwürfe"],
  ["Sent", "Sent", "Gesendet"],
  ["Junk", "Junk", "Spam"],
  ["Trash", "Trash", "Papierkorb"],
  ["Archive", "Archive", "Archiv"],
  ["Archive/2025", "2025", "2025"],
  ["Archive/2026", "2026", "2026"],
  ["Projects", "Projects", "Projekte"],
  ["Projects/Website relaunch", "Website relaunch", "Website-Relaunch"],
  ["Family", "Family", "Familie"],
  ["Travel", "Travel", "Reisen"],
  ["Reading", "Reading", "Lesestoff"],
];

export function mockRcmail(getLang: () => Lang, task = "mail"): Rcmail {
  const mailboxes = (): Record<string, Mailbox> =>
    Object.fromEntries(FOLDERS.map(([id, en, de]) => [id, { id, name: getLang() === "de" ? de : en }]));
  const env = {
    skin: "lumen",
    task,
    action: "",
    mailbox: "INBOX",
    delimiter: "/",
    get mailboxes() {
      return task === "mail" ? mailboxes() : undefined;
    },
    mailboxes_list: FOLDERS.map(([id]) => id),
  };
  const commands: Record<string, boolean> = {
    compose: true, checkmail: task === "mail", list: task === "mail", search: true, mail: true, addressbook: true,
    settings: true, about: true, logout: true, "switch-task": true,
  };
  return {
    env,
    commands,
    command(name: string, props?: unknown) {
      window.dispatchEvent(new CustomEvent("lumen-gallery-command", { detail: { name, props } }));
      return true;
    },
    get_label(name: string) {
      const lang = getLang();
      return data.labels[lang][name] ?? CORE[lang][name] ?? name;
    },
  };
}
