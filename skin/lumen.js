/*
 * Lumen skin for Roundcube Webmail: logo and browser colour helper.
 * Copyright (c) 2026 Paul Pasaurek. MIT licence, https://github.com/luminare-dev/lumen-mail
 *
 * Elastic's templates ask for /images/logo.svg, and Roundcube resolves that path in Elastic's
 * folder first, so a skin that extends Elastic cannot replace the logo by shipping a file of
 * the same name. This script runs from Lumen's footer wrapper, before Elastic's ui.js starts,
 * and swaps Elastic's default logo for the Luminare logo:
 *   - only when the page shows Elastic's default logo, so a logo the admin set with the
 *     skin_logo option always wins;
 *   - it fills rcmail.env.additional_logos only when the admin set no logo variant at all, so
 *     ui.js switches to the compact logo on phones as it does for Elastic. ui.js prefers
 *     small-dark, then small, then dark: a variant filled next to one the admin set would win
 *     over the admin's choice.
 * The menu rail and the login hero are Night in both colour modes, so the same image serves
 * light and dark mode. The image URLs come from data-src-* attributes on this script tag,
 * which Roundcube resolves (and cache-busts) like any other skin asset.
 *
 * It also keeps the browser's theme-color in step with the page. meta.json's theme-color tags
 * follow the system setting, but Elastic switches colour modes with its own setting (the
 * html.dark-mode class) and never updates theme-color. The login page is Night in both modes.
 */
(function () {
    'use strict';

    var script = document.currentScript;
    var rc = window.rcmail;
    if (!script || !rc || !rc.env) {
        return;
    }

    var root = document.documentElement;
    var login = rc.env.task === 'login' || /\btask-login\b/.test(document.body.className);

    function themeColor() {
        var color = login || root.classList.contains('dark-mode') ? '#0A1224' : '#F3F6FB';
        var metas = document.querySelectorAll('meta[name="theme-color"]');
        for (var i = 0; i < metas.length; i++) {
            metas[i].removeAttribute('media');
            if (metas[i].getAttribute('content') !== color) {
                metas[i].setAttribute('content', color);
            }
        }
    }
    themeColor();
    if (!login && typeof window.MutationObserver === 'function') {
        new window.MutationObserver(themeColor).observe(root, { attributes: true, attributeFilter: ['class'] });
    }

    var logo = document.getElementById('logo');
    var elasticDefault = /(^|\/)skins\/elastic\/images\/logo\.svg(\?|#|$)/;
    if (!logo || !elasticDefault.test(logo.getAttribute('src') || '')) {
        return;
    }

    var main = script.getAttribute(login ? 'data-src-login' : 'data-src-app');
    var compact = script.getAttribute('data-src-compact');
    if (!main) {
        return;
    }

    logo.setAttribute('src', main);
    logo.setAttribute('alt', 'Luminare');
    logo.classList.add('lumen-logo');

    var logos = rc.env.additional_logos || {};
    if (Object.keys(logos).length === 0) {
        rc.env.additional_logos = { dark: main, small: compact || main, 'small-dark': compact || main };
    }
})();
