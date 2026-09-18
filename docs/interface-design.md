# Petey interface design

Petey should feel like a personal desktop space. Use restrained surfaces, readable text, one accent for actions and selection, and plain labels that describe what the user can do.

## Settings map

Settings opens to an overview with common tasks and three groups:

| Group | Category | What belongs here |
| --- | --- | --- |
| Your companion | Appearance & profile | Theme, window behavior, display scale, user name |
| Your companion | Personality & voice | Character, instructions, communication style, voice and persona snapshots |
| Your companion | Microphone | Listening mode, audio device, sensitivity and microphone test |
| Connections | Models & API keys | All service credentials and provider/model choices |
| Connections | Tools & integrations | Filesystem MCP, approved-folder access, link to Add-ons |
| Your data | Knowledge files | Reference files and testing what Petey can find |
| Your data | Memory & privacy | Storage counts and explicit data removal controls |

Each page uses the same header, category navigation, search, save guidance, bounded
content width, and section links. Common controls are open; advanced provider
options and destructive actions use disclosures. Save behavior remains explicit:
theme/window preferences and connection switches apply immediately; other forms
retain their named Save buttons. Personality and voice can still save together.

## Extending settings

- Add a page to `web/settings_pages.py` with an ID, title, description, summary,
  icon, group, and save hint. Add its content in `web/templates/settings/<id>.html`.
  `settings/shell.html` renders the shared shell; overview/navigation follow the
  catalog automatically. Client routes are derived from `.app-view` elements.
- Add sections with `.settings-card`, a stable unique `id`, and an `h2`. Use
  `.settings-section`/`.settings-section-body` for disclosures, `.field-grid` for
  forms, `.preference-row` for switches, and `.inline-actions` for save/test controls.
  Keep feedback next to the relevant actions using `.wide-status` and `role="status".
- `web/static/settings.js` generates section links and the search index. Optional
  `data-settings-keywords` supplies static synonyms. It indexes headings, labels,
  and category names, never field values, credentials, or uploaded content.
- Link to controls with `data-settings-view` and `data-settings-target`; do not
  duplicate them. `openSetting` finds the target's current page, expands ancestor
  disclosures, scrolls, and focuses the heading. Old section links keep working
  after a move. `#settings` opens the overview; `#appearance` opens display/profile.
- Feature loading/save handlers remain in `desktop.js`. A new setting still needs
  the state/API/validation coverage described in `AGENTS.md`.

Search remains available on compact screens, with horizontally scrollable category
navigation and keyboard access to results. Browser back/forward follows page
navigation. Keep API keys and provider choices centralized; use section links from
voice, microphone, memory, and Help.

Run `tests/test_settings_ui.py` for catalog, unique-ID, link-target and control
contracts; run the desktop API tests for saving behavior. Browser checks must cover
category navigation, search/deep links, disclosures, save/reload, history, and compact
layouts. Use temporary data and mocked provider catalogs, never real keys or memory.

## Appearance

Use the semantic CSS tokens in `desktop.css` for surfaces, text, borders, accent, success, and danger. Midnight, Ocean, Forest, and Paper share the same layout and meaning. Paper is light; the others are dark. Media artwork and the visual-mode canvas retain their own colors.

Theme previews are native radio inputs with visible selection and keyboard focus. Theme changes preview immediately, persist through `/preferences`, and revert on failure. Server-render the saved theme to prevent a flash of the default palette. Other settings show explicit save controls; window preferences apply immediately.

Use clear focus indicators, native form controls, descriptive labels, and reduced-motion support. At narrow widths, settings categories become horizontally scrollable and the main app navigation remains available. Validate layouts at desktop and compact widths, including light-theme text contrast.

## Guidance consulted

- [Apple: Settings](https://developer.apple.com/design/human-interface-guidelines/settings) — organize app-wide preferences and avoid unnecessary choices.
- [GOV.UK: Accordion](https://design-system.service.gov.uk/components/accordion/) — use clear structure first; do not hide everything by default.
- [W3C: Radio group pattern](https://www.w3.org/WAI/ARIA/apg/patterns/radio/) — single-choice semantics and keyboard behavior for the theme selector.
