# Petey interface design

Petey should feel like a personal desktop space. Use restrained surfaces, readable text, one accent for actions and selection, and plain labels that describe what the user can do.

## Settings map

| Category | What belongs here |
| --- | --- |
| Appearance | Theme, window behavior, display scale, user name |
| Personality & voice | Character, instructions, communication style, voice and persona snapshots |
| Microphone | Listening mode, audio device, sensitivity and microphone test |
| Models & API keys | All service credentials and provider/model choices |
| Knowledge | Reference files and testing what Petey can find |
| Memory & privacy | Storage counts and explicit data removal controls |

Keep the category navigation consistent using the template's `settings_navigation` macro. Link related controls directly to their section using `data-settings-target`; do not duplicate controls. Settings search indexes headings and labels, never field values or credentials. Keep common tasks open and infrequent/destructive tasks in clearly labelled disclosures. Search must expand ancestor disclosures before focusing a result.

## Appearance

Use the semantic CSS tokens in `desktop.css` for surfaces, text, borders, accent, success, and danger. Midnight, Ocean, Forest, and Paper share the same layout and meaning. Paper is light; the others are dark. Media artwork and the visual-mode canvas retain their own colors.

Theme previews are native radio inputs with visible selection and keyboard focus. Theme changes preview immediately, persist through `/preferences`, and revert on failure. Server-render the saved theme to prevent a flash of the default palette. Other settings show explicit save controls; window preferences apply immediately.

Use clear focus indicators, native form controls, descriptive labels, and reduced-motion support. At narrow widths, settings categories become horizontally scrollable and the main app navigation remains available. Validate layouts at desktop and compact widths, including light-theme text contrast.

## Guidance consulted

- [Apple: Settings](https://developer.apple.com/design/human-interface-guidelines/settings) — organize app-wide preferences and avoid unnecessary choices.
- [GOV.UK: Accordion](https://design-system.service.gov.uk/components/accordion/) — use clear structure first; do not hide everything by default.
- [W3C: Radio group pattern](https://www.w3.org/WAI/ARIA/apg/patterns/radio/) — single-choice semantics and keyboard behavior for the theme selector.
