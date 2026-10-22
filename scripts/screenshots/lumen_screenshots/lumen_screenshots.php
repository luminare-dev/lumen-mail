<?php

/**
 * lumen_screenshots: invented example mail for the screenshots of the Lumen skin.
 *
 * A Roundcube plugin for a scratch copy of Roundcube that PHP's built-in web server (php -S)
 * serves on the loopback interface. It replaces the IMAP storage with an in-memory mailbox of
 * invented messages (example.com, example.net and example.org addresses), so any user name and
 * password log in and nothing connects to a mail server. Under any other web server, or for a
 * request from another address, it does nothing but log that it is inactive.
 *
 * Never enable it on a Roundcube that people use. How it is used: docs/development.md
 * ("Screenshots"). Part of lumen-mail, MIT licence, https://github.com/luminare-dev/lumen-mail
 */
class lumen_screenshots extends rcube_plugin
{
    public function init()
    {
        $remote = $_SERVER['REMOTE_ADDR'] ?? '';
        if (PHP_SAPI !== 'cli-server' || !in_array($remote, ['127.0.0.1', '::1'], true)) {
            rcube::write_log('errors', 'lumen_screenshots is inactive: it only runs under php -S on the loopback interface');

            return;
        }

        rcube::get_instance()->config->set('storage_driver', 'lumen_screenshots');
        $this->add_hook('user_create', [$this, 'user_create']);
    }

    /**
     * The identity's name: the example user's (alex@example.com -> Alex Morgan), otherwise the
     * address's local part.
     */
    public function user_create($args)
    {
        $user = (string) $args['user'];
        $args['user_name'] = lumen_screenshots_data::user_name($user)
            ?? ucwords(str_replace(['.', '_', '-'], ' ', strstr($user, '@', true) ?: $user));

        return $args;
    }
}

/**
 * The storage driver (storage_driver 'lumen_screenshots'): the example mailbox in memory. Flags a
 * user changes (read, flagged) are kept in the session; everything else is read only, and every
 * method not overridden here stays offline (check_connection() is false).
 */
class rcube_lumen_screenshots extends rcube_imap
{
    private const FLAGS = 'lumen_screenshots_flags';

    /** @var ?array Folder name => list of rcube_message_header, newest first */
    private $headers;

    /** @var array Folder name => uid => raw message source */
    private $raw = [];

    public function __construct()
    {
        parent::__construct();
        $this->delimiter = '/';
        $this->namespace = ['personal' => [['', '/']], 'other' => null, 'shared' => null,
            'prefix_in' => '', 'prefix_out' => ''];
    }

    public function connect($host, $user, $pass, $port = 143, $use_ssl = null)
    {
        $this->options['user'] = $user;
        $this->connect_done = true;

        return true;
    }

    public function close() {}

    public function is_connected()
    {
        return true;
    }

    public function check_connection()
    {
        return false;
    }

    public function get_error_code()
    {
        return 0;
    }

    public function get_error_str()
    {
        return '';
    }

    public function get_response_code()
    {
        return self::UNKNOWN;
    }

    public function get_vendor()
    {
        return '';
    }

    public function get_capability($cap)
    {
        return strtoupper($cap) === 'QUOTA';
    }

    public function check_permflag($flag)
    {
        return true;
    }

    public function get_hierarchy_delimiter()
    {
        return '/';
    }

    public function list_folders_subscribed($root = '', $name = '*', $filter = null, $rights = null, $skip_sort = false)
    {
        return $this->folder_names($name);
    }

    public function list_folders($root = '', $name = '*', $filter = null, $rights = null, $skip_sort = false)
    {
        return $this->folder_names($name);
    }

    public function folder_exists($folder, $subscription = false)
    {
        return in_array($folder, $this->folder_names('*'), true);
    }

    public function folder_attributes($folder, $force = false)
    {
        return [];
    }

    public function folder_namespace($folder)
    {
        return 'personal';
    }

    public function mod_folder($folder, $mode = 'out')
    {
        return $folder;
    }

    public function my_rights($folder)
    {
        return ['l', 'r', 's', 'w', 'i', 'p', 'k', 'x', 't', 'e', 'a'];
    }

    public function get_metadata($folder, $entries, $options = [], $force = false)
    {
        return [];
    }

    public function folder_data($folder)
    {
        $uids = array_map(static fn ($h) => $h->uid, $this->messages($folder));

        return ['UIDVALIDITY' => 1, 'UIDNEXT' => ($uids ? max($uids) : 0) + 1, 'EXISTS' => count($uids),
            'RECENT' => 0, 'PERMANENTFLAGS' => ['\*']];
    }

    public function folder_status($folder = null, &$diff = [])
    {
        return 0;
    }

    public function folder_sync($folder) {}

    public function folder_size($folder)
    {
        return array_sum(array_map(static fn ($h) => $h->size, $this->messages($folder)));
    }

    public function get_quota($folder = null)
    {
        $used = 1_258_291;  // KiB
        $total = 5_242_880;

        return ['used' => $used, 'total' => $total, 'percent' => (int) round($used / $total * 100),
            'all' => ['' => ['storage' => ['used' => $used, 'total' => $total]]]];
    }

    public function count($folder = null, $mode = 'ALL', $force = false, $status = true)
    {
        $messages = $this->messages($folder);
        switch (strtoupper($mode)) {
            case 'UNSEEN':
                return count(array_filter($messages, static fn ($h) => empty($h->flags['SEEN'])));
            case 'RECENT':
                return 0;
            default:
                return count($messages);
        }
    }

    public function list_messages($folder = null, $page = null, $sort_field = null, $sort_order = null, $slice = 0)
    {
        $messages = $this->messages($folder);
        if (strtoupper((string) ($sort_order ?: $this->sort_order)) === 'ASC') {
            $messages = array_reverse($messages);
        }

        $page = $page ?: $this->list_page;
        $list = array_slice($messages, ($page - 1) * $this->page_size, $this->page_size);

        return $slice ? array_slice($list, -$slice, $slice) : $list;
    }

    public function index($folder = null, $sort_field = null, $sort_order = null, $no_threads = false, $no_search = false)
    {
        $uids = array_map(static fn ($h) => $h->uid, $this->list_messages($folder, 1, $sort_field, $sort_order));

        return new rcube_result_index($this->folder_name($folder), '* SORT ' . implode(' ', $uids));
    }

    public function list_flags($folder, $uids, $mod_seq = null)
    {
        $flags = [];
        foreach ($this->messages($folder) as $h) {
            $flags[$h->uid] = $h->flags;
        }

        return $flags;
    }

    public function get_message_headers($uid, $folder = null, $force = false)
    {
        foreach ($this->messages($folder) as $h) {
            if ((string) $h->uid === (string) $uid) {
                return clone $h;
            }
        }

        return false;
    }

    public function get_message($uid, $folder = null)
    {
        $headers = $this->get_message_headers($uid, $folder);
        if (!$headers) {
            return false;
        }

        $struct = rcube_mime::parse_message($this->raw[$headers->folder][$headers->uid]);
        if (empty($struct->parts)) {
            $struct->mime_id = '1';
        }
        $headers->structure = $struct;

        return $headers;
    }

    public function get_message_part($uid, $part, $o_part = null, $print = null, $fp = null,
        $skip_charset_conv = false, $max_bytes = 0, $formatted = true)
    {
        $message = $this->get_message($uid);
        $body = $message ? $this->find_part($message->structure, (string) $part) : null;
        if ($body === null) {
            return false;
        }
        if ($fp) {
            fwrite($fp, $body);

            return true;
        }
        if ($print) {
            echo $body;

            return true;
        }

        return $body;
    }

    public function get_raw_body($uid, $fp = null, $part = null)
    {
        $headers = $this->get_message_headers($uid);
        $raw = $headers ? $this->raw[$headers->folder][$headers->uid] : false;
        if ($raw !== false && $fp) {
            fwrite($fp, $raw);

            return true;
        }

        return $raw;
    }

    public function get_raw_headers($uid, $part = null)
    {
        $raw = $this->get_raw_body($uid);

        return $raw === false ? false : substr($raw, 0, strpos($raw, "\r\n\r\n") + 2);
    }

    public function print_raw_body($uid, $formatted = true)
    {
        echo (string) $this->get_raw_body($uid);
    }

    public function set_flag($uids, $flag, $folder = null, $skip_cache = false)
    {
        $folder = $this->folder_name($folder);
        $flag = strtoupper($flag);
        $set = !str_starts_with($flag, 'UN');
        $name = $set ? $flag : substr($flag, 2);
        $all = array_map(static fn ($h) => (string) $h->uid, $this->messages($folder));
        $uids = $uids === '*' ? $all : (is_array($uids) ? $uids : explode(',', (string) $uids));

        foreach ($uids as $uid) {
            $_SESSION[self::FLAGS][$folder][(string) $uid][$name] = $set;
        }
        $this->headers = null;

        return true;
    }

    private function find_part($part, string $mime_id)
    {
        if ((string) $part->mime_id === $mime_id || ($mime_id === '' && empty($part->parts))) {
            return is_string($part->body) ? $part->body : null;
        }
        foreach ((array) $part->parts as $child) {
            if (($body = $this->find_part($child, $mime_id)) !== null) {
                return $body;
            }
        }

        return null;
    }

    private function folder_name($folder): string
    {
        return is_string($folder) && strlen($folder) ? $folder : (string) $this->folder;
    }

    private function folder_names($name): array
    {
        $names = array_keys($this->data()['folders']);
        if ($name === '*' || $name === '%') {
            return $names;
        }

        return in_array($name, $names, true) ? [$name] : [];
    }

    private function data(): array
    {
        $user = (string) ($this->options['user'] ?? $_SESSION['username'] ?? '');

        return lumen_screenshots_data::for_user($user, (string) ($_SESSION['language'] ?? 'en_US'));
    }

    /**
     * @return rcube_message_header[] newest first
     */
    private function messages($folder): array
    {
        if ($this->headers === null) {
            $this->headers = [];
            $data = $this->data();
            $saved = $_SESSION[self::FLAGS] ?? [];
            foreach ($data['folders'] as $name => $messages) {
                $this->headers[$name] = [];
                $uid = count($messages);
                foreach ($messages as $seq => $m) {
                    $raw = lumen_screenshots_data::raw_message($m, $data['user'], $name, $uid);
                    $h = new rcube_message_header();
                    $h->id = count($messages) - $seq;
                    $h->uid = $uid;
                    $h->folder = $name;
                    $h->subject = lumen_screenshots_data::encode($m['subject']);
                    $h->from = lumen_screenshots_data::address($m['from']);
                    $h->to = lumen_screenshots_data::address($data['user']);
                    $h->date = $h->internaldate = $m['date']->format('r');
                    $h->timestamp = $m['date']->getTimestamp();
                    $h->messageID = sprintf('<%d.%s@example.com>', $uid, md5($name));
                    $h->size = strlen($raw);
                    $h->charset = 'UTF-8';
                    $h->ctype = $m['attachment'] ? 'multipart/mixed' : ($m['plain'] ? 'text/plain' : 'multipart/alternative');
                    $h->flags = [];
                    foreach ($m['flags'] as $f) {
                        $h->flags[$f] = true;
                    }
                    foreach ($saved[$name][(string) $uid] ?? [] as $f => $on) {
                        if ($on) {
                            $h->flags[$f] = true;
                        } else {
                            unset($h->flags[$f]);
                        }
                    }
                    $this->headers[$name][] = $h;
                    $this->raw[$name][$uid] = $raw;
                    $uid--;
                }
            }
        }

        return $this->headers[$this->folder_name($folder)] ?? [];
    }
}

/**
 * The invented example data: people, folders and messages in English and German. Dates are
 * whole days before today (UTC), at office hours, so the list never shows a time in the future.
 */
class lumen_screenshots_data
{
    // The example users: each gets its own data set (any password); any other name gets the data
    // set of its language.
    private const USERS = [
        'en' => ['Alex Morgan', 'alex@example.com'],
        'de' => ['Jana Berger', 'jana@example.com'],
    ];

    private const PEOPLE = [
        'mira' => ['Mira Castell', 'mira.castell@example.com'],
        'jonas' => ['Jonas Weber', 'jonas.weber@example.net'],
        'priya' => ['Priya Raman', 'priya.raman@example.org'],
        'tomas' => ['Tomás Ortega', 'tomas.ortega@example.net'],
        'lena' => ['Lena Hofmann', 'lena.hofmann@example.org'],
        'sam' => ['Sam Okafor', 'sam.okafor@example.net'],
        'anna' => ['Anna Lindqvist', 'anna.lindqvist@example.com'],
        'office' => ['Office team|Büroteam', 'office@example.com'],
        'calendar' => ['Calendar|Kalender', 'calendar@example.com'],
        'helpdesk' => ['Helpdesk', 'helpdesk@example.com'],
        'digest' => ['Example Weekly|Wochenpost', 'digest@example.org'],
        'it' => ['IT team|IT-Team', 'it@example.com'],
    ];

    public static function for_user(string $user, string $language): array
    {
        $de = strcasecmp($user, self::USERS['de'][1]) === 0
            || (strcasecmp($user, self::USERS['en'][1]) !== 0 && str_starts_with($language, 'de'));
        $today = new DateTimeImmutable('today', new DateTimeZone('UTC'));
        $folders = [];
        foreach (($de ? self::german() : self::english()) as $folder => $messages) {
            $folders[$folder] = [];
            foreach ($messages as [$days, $time, $who, $subject, $flags, $body, $options]) {
                [$hour, $minute] = array_map('intval', explode(':', $time));
                $person = self::PEOPLE[$who];
                $names = explode('|', $person[0]);
                $folders[$folder][] = [
                    'date' => $today->modify("-{$days} days")->setTime($hour, $minute),
                    'from' => [$names[$de && isset($names[1]) ? 1 : 0], $person[1]],
                    'subject' => $subject,
                    'flags' => array_filter(explode(' ', $flags)),
                    'body' => $body,
                    'attachment' => $options['attachment'] ?? null,
                    'plain' => !empty($options['plain']),
                ];
            }
        }

        return ['user' => self::USERS[$de ? 'de' : 'en'], 'folders' => $folders];
    }

    public static function user_name(string $email): ?string
    {
        foreach (self::USERS as [$name, $address]) {
            if (strcasecmp($address, $email) === 0) {
                return $name;
            }
        }

        return null;
    }

    public static function encode(string $text): string
    {
        return preg_match('/[^\x20-\x7e]/', $text) ? '=?UTF-8?B?' . base64_encode($text) . '?=' : $text;
    }

    public static function address(array $person): string
    {
        return self::encode($person[0]) . ' <' . $person[1] . '>';
    }

    public static function raw_message(array $m, array $user, string $folder, int $uid): string
    {
        $head = [
            'Date: ' . $m['date']->format('r'),
            'From: ' . self::address($m['from']),
            'To: ' . self::address($user),
            'Subject: ' . self::encode($m['subject']),
            sprintf('Message-ID: <%d.%s@example.com>', $uid, md5($folder)),
            'MIME-Version: 1.0',
        ];
        $text = "Content-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"
            . str_replace("\n", "\r\n", $m['body']) . "\r\n";
        // text only, or text and HTML as most mail programs send it
        $alt = '=_alt_' . md5($folder . $uid);
        $body = $m['plain'] ? $text : "Content-Type: multipart/alternative; boundary=\"{$alt}\"\r\n\r\n"
            . "--{$alt}\r\n" . $text
            . "--{$alt}\r\nContent-Type: text/html; charset=UTF-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"
            . self::html($m['body']) . "\r\n"
            . "--{$alt}--\r\n";
        if (empty($m['attachment'])) {
            return implode("\r\n", $head) . "\r\n" . $body;
        }

        $mixed = '=_mixed_' . md5($folder . $uid);
        $file = $m['attachment'];

        return implode("\r\n", $head) . "\r\n"
            . "Content-Type: multipart/mixed; boundary=\"{$mixed}\"\r\n\r\n"
            . "--{$mixed}\r\n" . $body
            . "--{$mixed}\r\n"
            . "Content-Type: application/pdf; name=\"{$file}\"\r\n"
            . "Content-Disposition: attachment; filename=\"{$file}\"\r\n"
            . "Content-Transfer-Encoding: base64\r\n\r\n"
            . chunk_split(base64_encode(self::pdf($m['subject'], $m['body'])), 76, "\r\n")
            . "--{$mixed}--\r\n";
    }

    /**
     * The HTML part: a paragraph per block, numbered lines as a list, wrapped lines joined.
     */
    private static function html(string $text): string
    {
        $blocks = [];
        foreach (preg_split('/\n{2,}/', trim($text)) as $block) {
            $lines = array_map(static fn ($l) => htmlspecialchars($l, ENT_QUOTES, 'UTF-8'), explode("\n", $block));
            if (count(preg_grep('/^\d+\. /', $lines)) === count($lines)) {
                $items = array_map(static fn ($l) => '<li>' . preg_replace('/^\d+\. /', '', $l) . '</li>', $lines);
                $blocks[] = '<ol>' . implode('', $items) . '</ol>';
                continue;
            }
            $html = '';
            foreach ($lines as $i => $line) {
                // a line close to the wrap width continues on the next line; a short one ends there
                $html .= $line . ($i === count($lines) - 1 ? '' : (mb_strlen($line) > 60 ? ' ' : '<br>'));
            }
            $blocks[] = '<p>' . $html . '</p>';
        }

        return "<!DOCTYPE html>\r\n<html><head><meta charset=\"UTF-8\"></head><body>\r\n"
            . implode("\r\n", $blocks) . "\r\n</body></html>";
    }

    /**
     * A one-page PDF with the subject and the text, so the attachment opens like a real one.
     */
    private static function pdf(string $title, string $body): string
    {
        $text = 'BT /F1 12 Tf 72 770 Td 16 TL';
        foreach (array_merge([$title, ''], explode("\n", $body)) as $i => $line) {
            $line = addcslashes(preg_replace('/[^\x20-\x7e]/', '?', $line), '()\\');
            $text .= " ({$line}) " . ($i === 0 ? 'Tj' : "'");
        }
        $text .= ' ET';
        $objects = [
            '<< /Type /Catalog /Pages 2 0 R >>',
            '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R'
                . ' /Resources << /Font << /F1 5 0 R >> >> >>',
            '<< /Length ' . strlen($text) . " >>\nstream\n" . $text . "\nendstream",
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        ];
        $pdf = "%PDF-1.4\n";
        $offsets = [];
        foreach ($objects as $i => $object) {
            $offsets[] = strlen($pdf);
            $pdf .= ($i + 1) . " 0 obj\n" . $object . "\nendobj\n";
        }
        $xref = strlen($pdf);
        $pdf .= 'xref' . "\n0 " . (count($objects) + 1) . "\n0000000000 65535 f \n";
        foreach ($offsets as $offset) {
            $pdf .= sprintf("%010d 00000 n \n", $offset);
        }

        return $pdf . 'trailer' . "\n<< /Size " . (count($objects) + 1) . " /Root 1 0 R >>\nstartxref\n{$xref}\n%%EOF\n";
    }

    // [days before today, time (UTC), sender, subject, flags, body, options]; options: 'attachment' (a
    // PDF of that name), 'plain' (text only; every other message has a text and an HTML part)

    private static function english(): array
    {
        return [
            'INBOX' => [
                [1, '16:42', 'mira', 'Design review moved to Thursday', 'FLAGGED',
                    "Hi Alex,\n\nthe design review moves to Thursday at 14:00, same room. The slides are in\nthe shared folder; comments are welcome until Wednesday evening.\n\nMira", null],
                [1, '15:10', 'jonas', 'Agenda for the planning day', '',
                    "Hi Alex,\n\nhere is the agenda for next Tuesday's planning day. We start at 9:30 in the\nlarge meeting room, lunch is at 12:30.\n\n1. Looking back at the last quarter\n2. Goals for the next quarter\n3. Roles in the team\n4. Open questions\n\nPlease add your topics to the attached agenda by Monday.\n\nBest,\nJonas", ['attachment' => 'agenda.pdf']],
                [1, '11:25', 'priya', 'Re: Accessibility checklist for the new forms', 'SEEN ANSWERED',
                    "Thanks, Alex. I added the focus order and the error messages to the\nchecklist. Could you look at the colour contrast part?\n\nPriya", null],
                [1, '09:03', 'office', 'Kitchen closed on Friday afternoon', 'SEEN',
                    "Hello everyone,\n\nthe kitchen is cleaned on Friday from 13:00. There is coffee on the second\nfloor.\n\nThe office team", null],
                [2, '17:31', 'tomas', 'Photos from the team day', 'SEEN',
                    "Hi all,\n\nthe photos from the team day are in the attached overview. Thanks for a\ngreat day!\n\nTomás", ['attachment' => 'team-day.pdf']],
                [2, '08:00', 'calendar', 'Reminder: quarterly review on Friday at 10:00', 'SEEN',
                    "Quarterly review\nFriday, 10:00 to 11:30, large meeting room", ['plain' => true]],
                [3, '14:12', 'lena', 'Draft: release notes for version 2.4', '',
                    "Hi Alex,\n\nthe draft of the release notes is below and attached. Could you check the\nsection about the new settings page before Friday?\n\nVersion 2.4\n-----------\n\nNew\n- A settings page for notifications\n- Keyboard shortcuts for the most used actions\n- Dark mode for the reports\n\nFixed\n- The export keeps the column order\n- The calendar shows dates in your time zone\n\nThanks,\nLena",
                    ['attachment' => 'release-notes-2.4.pdf', 'plain' => true]],
                [3, '10:47', 'helpdesk', 'Ticket 4821 closed: VPN access', 'SEEN',
                    "Hello Alex,\n\nyour VPN access works again. We closed ticket 4821.\n\nHelpdesk", ['plain' => true]],
                [4, '12:05', 'sam', 'Lunch on Wednesday?', 'SEEN ANSWERED',
                    "Hi Alex,\n\nlunch on Wednesday at 12:15? The new place around the corner has a garden.\n\nSam", null],
                [5, '07:15', 'digest', 'Five ideas for a calmer inbox', 'SEEN',
                    "1. Turn off notifications you never read.\n2. Use folders for projects.\n3. Answer short questions at once.\n4. Archive what is done.\n5. Close the mail tab while you focus.", null],
                [6, '09:30', 'mira', "Notes from Monday's stand-up", 'SEEN',
                    "Hi team,\n\nthe notes from Monday's stand-up are in the wiki.\n\nMira", null],
                [8, '16:20', 'anna', 'Welcome to the team!', 'SEEN FLAGGED',
                    "Hi Alex,\n\nwelcome to the team! Your desk is next to the window. See you on Monday.\n\nAnna", null],
                [9, '11:00', 'it', 'Your new laptop is ready', 'SEEN',
                    "Hello Alex,\n\nyour new laptop is ready. Please pick it up at the IT desk on the first\nfloor.\n\nIT team", null],
                [12, '13:45', 'jonas', 'Room booking for the workshop', 'SEEN',
                    "Hi Alex,\n\nI booked the large meeting room for the workshop on the 14th.\n\nJonas", null],
            ],
            'Drafts' => [],
            'Sent' => [],
            'Junk' => [],
            'Trash' => [],
            'Archive' => [],
            'Projects' => [
                [1, '10:15', 'lena', 'Homepage text for review', '',
                    "Hi Alex,\n\nthe new homepage text is ready for review.\n\nLena", null],
                [2, '14:50', 'tomas', 'New photos for the website', '',
                    "Hi Alex,\n\nthe new photos for the website are in the shared folder.\n\nTomás", null],
            ],
            'Projects/Website' => [],
            'Travel' => [],
        ];
    }

    private static function german(): array
    {
        return [
            'INBOX' => [
                [1, '16:42', 'mira', 'Design-Review auf Donnerstag verschoben', 'FLAGGED',
                    "Hallo Jana,\n\ndas Design-Review ist jetzt am Donnerstag um 14:00, im selben Raum. Die Folien\nliegen im gemeinsamen Ordner; Anmerkungen gern bis Mittwochabend.\n\nMira", null],
                [1, '15:10', 'jonas', 'Agenda für den Planungstag', '',
                    "Hallo Jana,\n\nhier ist die Agenda für den Planungstag am Dienstag. Wir beginnen um 9:30\nim großen Besprechungsraum, Mittagessen gibt es um 12:30.\n\n1. Rückblick auf das letzte Quartal\n2. Ziele für das nächste Quartal\n3. Rollen im Team\n4. Offene Fragen\n\nBitte ergänze deine Themen bis Montag in der angehängten Agenda.\n\nViele Grüße\nJonas", ['attachment' => 'agenda.pdf']],
                [1, '11:25', 'priya', 'Re: Checkliste Barrierefreiheit für die neuen Formulare', 'SEEN ANSWERED',
                    "Danke, Jana. Ich habe die Fokusreihenfolge und die Fehlermeldungen ergänzt.\nKannst du dir den Teil zum Farbkontrast ansehen?\n\nPriya", null],
                [1, '09:03', 'office', 'Küche am Freitagnachmittag geschlossen', 'SEEN',
                    "Hallo zusammen,\n\ndie Küche wird am Freitag ab 13:00 gereinigt. Kaffee gibt es im zweiten Stock.\n\nEuer Büroteam", null],
                [2, '17:31', 'tomas', 'Fotos vom Teamtag', 'SEEN',
                    "Hallo zusammen,\n\ndie Fotos vom Teamtag sind in der angehängten Übersicht. Danke für den\nschönen Tag!\n\nTomás", ['attachment' => 'teamtag.pdf']],
                [2, '08:00', 'calendar', 'Erinnerung: Quartalsrückblick am Freitag um 10:00', 'SEEN',
                    "Quartalsrückblick\nFreitag, 10:00 bis 11:30, großer Besprechungsraum", ['plain' => true]],
                [3, '14:12', 'lena', 'Entwurf: Versionshinweise für 2.4', '',
                    "Hallo Jana,\n\nder Entwurf der Versionshinweise steht unten und im Anhang. Kannst du den\nAbschnitt zur neuen Einstellungsseite bis Freitag prüfen?\n\nVersion 2.4\n-----------\n\nNeu\n- Eine Einstellungsseite für Benachrichtigungen\n- Tastenkürzel für die häufigsten Aktionen\n- Dunkler Modus für die Berichte\n\nBehoben\n- Der Export behält die Reihenfolge der Spalten\n- Der Kalender zeigt Daten in deiner Zeitzone\n\nDanke,\nLena",
                    ['attachment' => 'versionshinweise-2.4.pdf', 'plain' => true]],
                [3, '10:47', 'helpdesk', 'Ticket 4821 geschlossen: VPN-Zugang', 'SEEN',
                    "Hallo Jana,\n\ndein VPN-Zugang funktioniert wieder. Wir haben Ticket 4821 geschlossen.\n\nHelpdesk", ['plain' => true]],
                [4, '12:05', 'sam', 'Mittagessen am Mittwoch?', 'SEEN ANSWERED',
                    "Hallo Jana,\n\nMittagessen am Mittwoch um 12:15? Das neue Lokal um die Ecke hat einen Garten.\n\nSam", null],
                [5, '07:15', 'digest', 'Fünf Ideen für ein ruhigeres Postfach', 'SEEN',
                    "1. Schalte Benachrichtigungen ab, die du nie liest.\n2. Nutze Ordner für Projekte.\n3. Beantworte kurze Fragen sofort.\n4. Archiviere, was erledigt ist.\n5. Schließe den Mail-Tab, wenn du dich konzentrierst.", null],
                [6, '09:30', 'mira', 'Notizen vom Stand-up am Montag', 'SEEN',
                    "Hallo Team,\n\ndie Notizen vom Stand-up am Montag stehen im Wiki.\n\nMira", null],
                [8, '16:20', 'anna', 'Willkommen im Team!', 'SEEN FLAGGED',
                    "Hallo Jana,\n\nwillkommen im Team! Dein Platz ist am Fenster. Bis Montag!\n\nAnna", null],
                [9, '11:00', 'it', 'Dein neuer Laptop liegt bereit', 'SEEN',
                    "Hallo Jana,\n\ndein neuer Laptop liegt bereit. Du kannst ihn am IT-Schalter im ersten\nStock abholen.\n\nIT-Team", null],
                [12, '13:45', 'jonas', 'Raumbuchung für den Workshop', 'SEEN',
                    "Hallo Jana,\n\nich habe den großen Besprechungsraum für den Workshop am 14. gebucht.\n\nJonas", null],
            ],
            'Drafts' => [],
            'Sent' => [],
            'Junk' => [],
            'Trash' => [],
            'Archiv' => [],
            'Projekte' => [
                [1, '10:15', 'lena', 'Text der Startseite zur Durchsicht', '',
                    "Hallo Jana,\n\nder neue Text der Startseite ist bereit zur Durchsicht.\n\nLena", null],
                [2, '14:50', 'tomas', 'Neue Fotos für die Website', '',
                    "Hallo Jana,\n\ndie neuen Fotos für die Website liegen im gemeinsamen Ordner.\n\nTomás", null],
            ],
            'Projekte/Website' => [],
            'Reisen' => [],
        ];
    }
}
