// Test fixtures: a mocked rcmail (the parts of Roundcube's client API the palette uses) and
// representative page markup with the ids and classes of Elastic's task menu, list headers and
// settings menu. The markup is written for these tests; it is not copied from Elastic.

import { vi } from "vitest";
import type { Mailbox, Rcmail, RcmailEnv } from "../src/types";

export const LABELS_EN: Record<string, string> = {
  "lumen.palette_open": "Open the command palette",
  "lumen.palette_trigger": "Jump to",
  "lumen.palette_title": "Command palette",
  "lumen.palette_placeholder": "Search folders, settings and actions",
  "lumen.palette_empty": "No matches",
  "lumen.palette_results": "Results: $n",
  "lumen.palette_hint": "Arrow keys to move, Enter to open, Esc to close",
  "lumen.palette_current": "current",
  "lumen.palette_group_tasks": "Go to",
  "lumen.palette_group_folders": "Folders",
  "lumen.palette_group_settings": "Settings",
  "lumen.palette_group_actions": "Actions",
  mail: "Mail",
  contacts: "Contacts",
  settings: "Settings",
  compose: "Compose",
  checkmail: "Check for new messages",
  search: "Search",
  inbox: "Inbox",
  about: "About",
  logout: "Logout",
  darkmode: "Dark mode",
  lightmode: "Light mode",
  preferences: "Preferences",
  folders: "Folders",
  identities: "Identities",
  responses: "Responses",
  close: "Close",
};

export const MAILBOXES: Record<string, Mailbox> = {
  INBOX: { id: "INBOX", name: "Inbox", level: 0 },
  Drafts: { id: "Drafts", name: "Drafts", level: 0 },
  Sent: { id: "Sent", name: "Sent", level: 0 },
  Junk: { id: "Junk", name: "Junk", level: 0 },
  Archive: { id: "Archive", name: "Archive", level: 0 },
  "Archive/2024": { id: "Archive/2024", name: "2024", level: 1 },
  Shared: { id: "Shared", name: "Shared", virtual: true, level: 0 },
  "Shared/Team": { id: "Shared/Team", name: "Team", level: 1 },
  "Entw&APw-rfe": { id: "Entw&APw-rfe", name: "Entwürfe alt", level: 0 },
};

export interface FakeRcmail extends Rcmail {
  command: ReturnType<typeof vi.fn<(command: string, props?: unknown) => unknown>>;
  labels: Record<string, string>;
}

export function fakeRcmail(
  options: { env?: Partial<RcmailEnv>; commands?: Record<string, boolean>; labels?: Record<string, string> } = {},
): FakeRcmail {
  const labels = { ...LABELS_EN, ...options.labels };
  return {
    env: {
      skin: "lumen",
      task: "mail",
      action: "",
      mailbox: "INBOX",
      delimiter: "/",
      mailboxes: MAILBOXES,
      mailboxes_list: Object.keys(MAILBOXES),
      ...options.env,
    },
    commands: {
      compose: true,
      checkmail: true,
      list: true,
      search: true,
      mail: true,
      addressbook: true,
      settings: true,
      about: true,
      logout: true,
      "switch-task": true,
      ...options.commands,
    },
    labels,
    command: vi.fn<(command: string, props?: unknown) => unknown>(() => true),
    get_label: (name: string) => labels[name] ?? name,
  };
}

/** Elastic's task menu: core tasks, a plugin task, and the special buttons at the bottom. */
export const TASK_MENU = `
<div id="layout-menu">
  <div id="taskmenu" class="menu toolbar" role="navigation">
    <span class="action-buttons"><a class="compose" href="#"><span class="inner">Compose</span></a></span>
    <a class="mail selected" href="./?_task=mail"><span class="inner">Mail</span></a>
    <a class="contacts" href="./?_task=addressbook"><span class="inner">Contacts</span></a>
    <a class="calendar button-calendar" href="./?_task=calendar"><span class="inner">Calendar</span></a>
    <a class="disabled-plugin disabled" href="#"><span class="inner">Disabled plugin</span></a>
    <a class="settings" href="./?_task=settings"><span class="inner">Settings</span></a>
    <span class="special-buttons">
      <a class="theme dark" href="#"><span class="inner">Dark mode</span></a>
      <a class="about" href="#"><span class="inner">About</span></a>
      <a class="logout" href="./?_task=logout"><span class="inner">Logout</span></a>
    </span>
  </div>
</div>`;

export const MAIL_PAGE = `${TASK_MENU}
<div id="layout-list">
  <div class="searchbar menu"><input type="text" id="mailsearchform" name="_q"></div>
</div>
<div id="layout-content"><input type="text" id="subject" name="_subject"></div>`;

export const SETTINGS_PAGE = `${TASK_MENU}
<div id="layout-sidebar">
  <ul id="settings-menu" class="listing">
    <li id="settingstabpreferences" class="listitem preferences selected"><a href="./?_task=settings&_action=preferences">Preferences</a></li>
    <li id="settingstabfolders" class="listitem folders"><a href="./?_task=settings&_action=folders">Folders</a></li>
    <li id="settingstabidentities" class="listitem identities"><a href="./?_task=settings&_action=identities">Identities</a></li>
    <li id="settingstabpluginmanagesieve" class="listitem filter"><a href="./?_task=settings&_action=plugin.managesieve">Filters</a></li>
  </ul>
</div>
<div id="layout-list">
  <table id="sections-table"><tbody>
    <tr id="rcmrowgeneral" class="general"><td class="section">User Interface</td></tr>
    <tr id="rcmrowmailbox" class="mailbox selected"><td class="section">Mailbox View</td></tr>
  </tbody></table>
</div>`;
