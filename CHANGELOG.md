# Changelog

All notable changes to this project are listed here, newest first. The sections follow
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). release-please writes each entry from
the Conventional Commit titles of the merged pull requests; do not edit entries by hand.

<!-- release-please inserts each new release above the first line that starts with "## ["
     (or "## " and a digit). Keep the "Origin" entry below as the last entry of this file. -->

## [0.1.1](https://github.com/luminare-dev/lumen-mail/compare/v0.1.0...v0.1.1) (2026-10-22)


### Fixed

* **skin:** keep long labels readable instead of cutting them off ([#4](https://github.com/luminare-dev/lumen-mail/issues/4)) ([fcabc0a](https://github.com/luminare-dev/lumen-mail/commit/fcabc0a6123281e5c6b012055ba51c50b4ee5dd5))

## 0.1.0 (2026-10-21)


### Added

* **contrib:** add the sync path, timer and service units ([68ad8f5](https://github.com/luminare-dev/lumen-mail/commit/68ad8f59e317d412079928f973701bc38cd358cd))
* **gallery:** add the design-system gallery ([a9f626e](https://github.com/luminare-dev/lumen-mail/commit/a9f626e835b21e1dff27b632ee5eb09c495515ab))
* **generator:** build and verify skins/lumen against the installed Elastic ([c2a967f](https://github.com/luminare-dev/lumen-mail/commit/c2a967f755c2fa00c95e0c925b398448ee275444))
* **generator:** install, check, sync, rollback and uninstall the skin ([edfa729](https://github.com/luminare-dev/lumen-mail/commit/edfa7295408863fa3bea74de6a69d5a98b90266a))
* **palette:** add the Ctrl+K command palette as a skin asset ([9dc56a3](https://github.com/luminare-dev/lumen-mail/commit/9dc56a3032cbce15360ac4bab2b2fe465c259407))
* **skin:** add the Lumen tokens, Elastic variable overrides and component layer ([5350e6d](https://github.com/luminare-dev/lumen-mail/commit/5350e6dfba5c58e8b470bcf39397906f2cea4091))


### Fixed

* **gallery:** invented names in the sample mail, scheduler in the credits ([3ac255f](https://github.com/luminare-dev/lumen-mail/commit/3ac255f62ab0c1bdd3df7354d1d29b86e066b64c))
* **generator:** build at once when lumen is the system skin and no build exists ([8c39433](https://github.com/luminare-dev/lumen-mail/commit/8c39433331064b4e4549889e95e1491b822c746f))
* **generator:** cap the compile at a 256 MB heap and the unit at 300M ([12d20ac](https://github.com/luminare-dev/lumen-mail/commit/12d20ac8b32f28a19072dc6bb2b6277ba5040fa2))
* **generator:** check back-off and memory before waiting, precompile the runtime ([f5ddc6a](https://github.com/luminare-dev/lumen-mail/commit/f5ddc6a93eecd5703664f2b3c525f16fdfa01421))
* **generator:** include the command palette in every build ([95a6b2b](https://github.com/luminare-dev/lumen-mail/commit/95a6b2b4aa2e6e08bd3a0ced800e3d7d48b95975))
* **generator:** never run LESS plugins or read outside the build folders ([1fdd1d9](https://github.com/luminare-dev/lumen-mail/commit/1fdd1d9801931550eac303985a69af90cd7fe7d3))
* **generator:** refuse a command palette bundle built from other sources ([99f524d](https://github.com/luminare-dev/lumen-mail/commit/99f524dec00ac6c7600e3a95a4874885953e5bee))
* **generator:** resolve Elastic's url()s like Roundcube does ([2914d8b](https://github.com/luminare-dev/lumen-mail/commit/2914d8b9256d790118e3ad6f0d2443eda00963ef))
* **generator:** run as the Roundcube owner and keep webmail up after updates ([358faf1](https://github.com/luminare-dev/lumen-mail/commit/358faf120ea2eebc29096ae5e7e072033e2b10da))
* **generator:** say "compiled from two sources" in the CSS licence banner ([cb33e36](https://github.com/luminare-dev/lumen-mail/commit/cb33e36c1d78bbf5d9f02909a1e36d52f9fc5f64))
* **generator:** say so when the Roundcube owner cannot read the sources ([4182b9b](https://github.com/luminare-dev/lumen-mail/commit/4182b9bfe4bfd57d2da09ebceddb85123857fc92))
* **generator:** ship React's licence with every build ([0668434](https://github.com/luminare-dev/lumen-mail/commit/0668434aad54cc153b95cd91d0ae1ad95e72e3fd))
* **generator:** wait for files that are root-only while an update extracts ([f3a1b31](https://github.com/luminare-dev/lumen-mail/commit/f3a1b311e0c5e758cf8d2c01ec43436cd3e062c1))
* **palette:** listen for Ctrl+K again after a frame loads a new page ([1a567f8](https://github.com/luminare-dev/lumen-mail/commit/1a567f863c614d8c8bbfa986abfdc8bbfa9ab95a))
* **palette:** stay closed while a Roundcube modal dialog is open ([e88b87c](https://github.com/luminare-dev/lumen-mail/commit/e88b87c26b169751e1816400243a90d0944ad012))
* **skin:** keep the menu's bottom buttons under the rail on right-to-left pages ([b472678](https://github.com/luminare-dev/lumen-mail/commit/b47267873b6721206aa416d5f881f1bf307cbdc7))
* **skin:** respect partial admin logos and follow the colour mode in theme-color ([393630a](https://github.com/luminare-dev/lumen-mail/commit/393630ab1b317c1ceb2d36d648a5cdda4be81546))
* **skin:** visible focus in dark lists and input groups, readable deleted rows ([273b407](https://github.com/luminare-dev/lumen-mail/commit/273b407ef84d7b7c1006de18188095d41a84af84))

## [Origin] - created from oss-template

This repository was created from
[luminare-dev/oss-template](https://github.com/luminare-dev/oss-template). Releases are listed
above this entry.
