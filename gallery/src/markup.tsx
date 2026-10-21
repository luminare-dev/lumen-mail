// Representative Roundcube pages for the skin previews, written for the gallery. They use the
// structural ids and classes of Elastic's layout (#layout, #layout-menu, #layout-sidebar,
// #layout-list, #layout-content, .header, .listing, .formcontent, the login form ...) so that a
// built Lumen stylesheet styles them; they are not copies of Elastic's templates, and Elastic's
// scripts do not run here.

const LOGO = "skins/lumen/images/luminare-mark.svg";
const LOCKUP = "skins/lumen/images/luminare-lockup-horizontal-dark.svg";

function TaskMenu({ task, dark }: { task: "mail" | "settings"; dark: boolean }) {
  return (
    <div id="layout-menu">
      <div className="popover-header">
        <img id="logo" className="lumen-logo" src={LOGO} alt="Luminare" />
      </div>
      <div id="taskmenu" className="menu toolbar" role="navigation" aria-label="Tasks">
        <span className="action-buttons">
          <a className="compose" href="#compose">
            <span className="inner">Compose</span>
          </a>
        </span>
        <a className={task === "mail" ? "mail selected" : "mail"} href="#mail">
          <span className="inner">Mail</span>
        </a>
        <a className="contacts" href="#contacts">
          <span className="inner">Contacts</span>
        </a>
        <a className={task === "settings" ? "settings selected" : "settings"} href="#settings">
          <span className="inner">Settings</span>
        </a>
        <span className="special-buttons">
          <a className={dark ? "theme light" : "theme dark"} href="#theme">
            <span className="inner">{dark ? "Light mode" : "Dark mode"}</span>
          </a>
          <a className="about" href="#about">
            <span className="inner">About</span>
          </a>
          <a className="logout" href="#logout">
            <span className="inner">Logout</span>
          </a>
        </span>
      </div>
    </div>
  );
}

const MESSAGES: [string, string, string, string, boolean, boolean][] = [
  // from, subject, date, size, unread, flagged
  ["Mira Kovač", "Compiler notes for Friday", "10:42", "12 KB", true, false],
  ["Jonas Feld", "Re: Engine design, part two", "09:15", "48 KB", true, true],
  ["Team calendar", "Weekly planning: agenda", "Yesterday", "6 KB", false, false],
  ["Ines Laurent", "Review of the release checklist", "Yesterday", "220 KB", false, false],
  ["Theo Brandt", "Lab results and next steps", "Mon", "31 KB", false, true],
  ["Lena Ortiz", "Quarterly figures", "Sun", "9 KB", false, false],
  ["Sam Okafor", "Notes from the reading group", "Sat", "17 KB", false, false],
];

function MailPage({ dark }: { dark: boolean }) {
  return (
    <div id="layout">
      <TaskMenu task="mail" dark={dark} />
      <div id="layout-sidebar" className="listbox" role="navigation" aria-label="Folders">
        <div className="header">
          <span className="header-title username">user@example.com</span>
        </div>
        <div id="folderlist-content" className="scroller">
          <ul id="mailboxlist" className="treelist listing folderlist">
            {([
              ["inbox selected unread", "Inbox", "3"],
              ["drafts", "Drafts", ""],
              ["sent", "Sent", ""],
              ["junk", "Junk", ""],
              ["trash", "Trash", ""],
              ["archive", "Archive", ""],
              ["", "Projects", "1"],
              ["", "Travel", ""],
            ] as const).map(([cls, name, unread]) => (
              <li key={name} className={`mailbox ${cls}${unread && !cls.includes("unread") ? " unread" : ""}`}>
                <a href={`#${name}`}>
                  {name}
                  {unread && <span className="unreadcount skip-content">{unread}</span>}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <div className="footer small">
          <div id="quotadisplay" className="quota-widget">
            <span className="count">12% of 5 GB used</span>
          </div>
        </div>
      </div>
      <div id="layout-list" className="listbox selected">
        <div id="messagelist-header" className="header">
          <span className="header-title">Inbox</span>
          <div className="toolbar menu" role="toolbar">
            <a href="#select" className="select">
              <span className="inner">Select</span>
            </a>
            <a href="#threads" className="threads">
              <span className="inner">Threads</span>
            </a>
            <a href="#options" className="options">
              <span className="inner">Options</span>
            </a>
          </div>
          <a className="button icon toolbar-button refresh" href="#refresh">
            <span className="inner">Refresh</span>
          </a>
        </div>
        <div className="searchbar menu" role="search">
          <form className="form-inline" onSubmit={(e) => e.preventDefault()}>
            <input type="text" id="mailsearchform" placeholder="Search..." aria-label="Search" />
            <a className="button search" href="#search">
              <span className="inner">Search</span>
            </a>
          </form>
        </div>
        <div id="messagelist-content" className="scroller">
          <table id="messagelist" className="listing messagelist sortheader fixedheader withselection">
            <tbody>
              {MESSAGES.map(([from, subject, date, size, unread, flagged], i) => (
                <tr
                  key={subject}
                  className={["message", unread && "unread", flagged && "flagged", i === 0 && "selected focused"]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <td className="subject">
                    <span className="fromto skip-on-drag">
                      <span className="adr">
                        <span className="rcmContactAddress">{from}</span>
                      </span>
                    </span>
                    <span className="date skip-on-drag">{date}</span>
                    <span className="size skip-on-drag">{size}</span>
                    <span className={unread ? "msgicon status unread" : "msgicon status"} />
                    <span className="subject">
                      <a href={`#m${i}`}>
                        <span>{subject}</span>
                      </a>
                    </span>
                  </td>
                  <td className="flags">
                    <span className={flagged ? "flag flagged" : "flag"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div id="layout-content" role="main">
        <div className="header">
          <span className="header-title">Compiler notes for Friday</span>
          <div id="toolbar-menu" className="toolbar menu" role="toolbar">
            {["reply", "reply-all", "forward", "delete", "junk", "more"].map((name) => (
              <a key={name} className={name} href={`#${name}`}>
                <span className="inner">{name.replace("-", " ")}</span>
              </a>
            ))}
          </div>
        </div>
        <div className="formcontent">
          <h2 className="subject">Compiler notes for Friday</h2>
          <p>
            <strong>Mira Kovač</strong> to Jonas Feld, today 10:42
          </p>
          <div className="boxinformation">The message contains remote images. Show them?</div>
          <p>Hi Jonas,</p>
          <p>
            here are the notes from Thursday. The new pass shortens the build by a third; the open question is
            whether the error messages stay as clear. Let's look at it together on Friday.
          </p>
          <blockquote>
            <p>Can we keep the old flag for one more release?</p>
          </blockquote>
          <p>
            <a href="#link">Meeting notes</a> · <button className="btn btn-primary">Reply</button>{" "}
            <button className="btn btn-secondary">Forward</button>
          </p>
        </div>
      </div>
    </div>
  );
}

function SettingsPage({ dark }: { dark: boolean }) {
  return (
    <div id="layout">
      <TaskMenu task="settings" dark={dark} />
      <div id="layout-sidebar" className="listbox" role="navigation" aria-label="Settings">
        <div className="header">
          <span className="header-title">Settings</span>
        </div>
        <div className="scroller">
          <ul id="settings-menu" className="listing iconized settings-default-icon">
            {[
              ["preferences selected", "Preferences"],
              ["folders", "Folders"],
              ["identities", "Identities"],
              ["responses", "Responses"],
              ["filter", "Filters"],
              ["password", "Password"],
            ].map(([cls, name]) => (
              <li key={name} className={`listitem ${cls}`}>
                <a href={`#${name}`}>{name}</a>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div id="layout-list" className="listbox">
        <div className="header">
          <span className="header-title">Preferences</span>
        </div>
        <div className="scroller">
          <table id="sections-table" className="listing iconized settings-default-icon">
            <tbody>
              {["User Interface", "Mailbox View", "Displaying Messages", "Composing Messages", "Contacts", "Server Settings"].map(
                (name, i) => (
                  <tr key={name} className={i === 0 ? "general selected focused" : undefined}>
                    <td className="section">{name}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div id="layout-content" className="selected" role="main">
        <div className="header">
          <span className="header-title">User Interface</span>
        </div>
        <div className="formcontent">
          <form className="propform" onSubmit={(e) => e.preventDefault()}>
            <fieldset>
              <legend>Main Options</legend>
              <table className="propform">
                <tbody>
                  <tr>
                    <td className="title">
                      <label htmlFor="rcmfd_lang">Language</label>
                    </td>
                    <td>
                      <select id="rcmfd_lang" className="custom-select" defaultValue="en">
                        <option value="en">English (US)</option>
                        <option value="de">Deutsch (Deutsch)</option>
                      </select>
                    </td>
                  </tr>
                  <tr>
                    <td className="title">
                      <label htmlFor="rcmfd_refresh">Refresh (check for new messages, etc.)</label>
                    </td>
                    <td>
                      <input id="rcmfd_refresh" className="form-control" defaultValue="every 1 minute(s)" />
                    </td>
                  </tr>
                  <tr>
                    <td className="title">
                      <label htmlFor="rcmfd_pretty">Pretty dates</label>
                    </td>
                    <td>
                      <input id="rcmfd_pretty" type="checkbox" className="form-check-input custom-switch" defaultChecked />
                    </td>
                  </tr>
                </tbody>
              </table>
            </fieldset>
            <div className="formbuttons">
              <button type="submit" className="btn btn-primary submit">
                Save
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function LoginPage() {
  return (
    <div id="layout">
      <h1 className="voice">Luminare Webmail Login</h1>
      <div id="layout-content" className="selected no-navbar" role="main">
        <img id="logo" className="lumen-logo" src={LOCKUP} alt="Luminare" />
        <form id="login-form" name="login-form" method="post" className="propform" onSubmit={(e) => e.preventDefault()}>
          <table>
            <tbody>
              <tr>
                <td className="title">
                  <label htmlFor="rcmloginuser">Username</label>
                </td>
                <td className="input">
                  <input name="_user" id="rcmloginuser" required size={40} autoComplete="username" className="form-control" placeholder="Username" />
                </td>
              </tr>
              <tr>
                <td className="title">
                  <label htmlFor="rcmloginpwd">Password</label>
                </td>
                <td className="input">
                  <input name="_pass" id="rcmloginpwd" required size={40} type="password" autoComplete="current-password" className="form-control" placeholder="Password" />
                </td>
              </tr>
            </tbody>
          </table>
          <p className="formbuttons">
            <button type="submit" id="rcmloginsubmit" className="button mainaction submit btn btn-primary btn-lg text-uppercase w-100">
              Login
            </button>
          </p>
        </form>
        <div id="login-footer" role="contentinfo">
          Luminare Webmail
        </div>
      </div>
    </div>
  );
}

export function Page({ page, dark }: { page: string; dark: boolean }) {
  if (page === "settings") return <SettingsPage dark={dark} />;
  if (page === "login") return <LoginPage />;
  return <MailPage dark={dark} />;
}
