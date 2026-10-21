/*
 * Lumen skin for Roundcube Webmail: logo helper.
 * Copyright (c) 2026 Paul Pasaurek. MIT licence, https://github.com/luminare-dev/lumen-mail
 *
 * Elastic's templates ask for /images/logo.svg, and Roundcube resolves that path in Elastic's
 * folder first, so a skin that extends Elastic cannot replace the logo by shipping a file of
 * the same name. This script runs from Lumen's footer wrapper, before Elastic's ui.js starts,
 * and swaps Elastic's default logo for the Luminare logo:
 *   - only when the page shows Elastic's default logo, so a logo the admin set with the
 *     skin_logo option always wins;
 *   - it fills rcmail.env.additional_logos only for the logo types the admin did not set, so
 *     ui.js keeps switching to the compact logo on phones exactly as it does for Elastic.
 * The menu rail and the login hero are Night in both colour modes, so the same image serves
 * light and dark mode. The image URLs come from data-src-* attributes on this script tag,
 * which Roundcube resolves (and cache-busts) like any other skin asset.
 */
(function () {
    'use strict';

    var script = document.currentScript;
    var rc = window.rcmail;
    if (!script || !rc || !rc.env) {
        return;
    }

    var logo = document.getElementById('logo');
    var elasticDefault = /(^|\/)skins\/elastic\/images\/logo\.svg(\?|#|$)/;
    if (!logo || !elasticDefault.test(logo.getAttribute('src') || '')) {
        return;
    }

    var login = rc.env.task === 'login' || /\btask-login\b/.test(document.body.className);
    var main = script.getAttribute(login ? 'data-src-login' : 'data-src-app');
    var compact = script.getAttribute('data-src-compact');
    if (!main) {
        return;
    }

    logo.setAttribute('src', main);
    logo.setAttribute('alt', 'Luminare');
    logo.classList.add('lumen-logo');

    var logos = rc.env.additional_logos || {};
    var defaults = { dark: main, small: compact || main, 'small-dark': compact || main };
    Object.keys(defaults).forEach(function (type) {
        if (!logos[type]) {
            logos[type] = defaults[type];
        }
    });
    rc.env.additional_logos = logos;
})();
