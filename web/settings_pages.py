"""Settings navigation catalog. Each page owns a template with stable section IDs.

Add a page here and its template under templates/settings/. Navigation, overview,
search categories and client routing derive from this catalog/rendered markup.
Provider loading and save handlers remain in desktop.js.
"""

SETTINGS_GROUPS = ("Your companion", "Connections", "Your data")
SETTINGS_PAGES = (
    dict(id="settings", title="Settings", description="Make PETEY your own. Choose a category or find a specific setting.",
         summary="Browse all settings", icon="⚙", group="", save_hint=""),
    dict(id="appearance", title="Appearance & profile", description="Your name, your theme, and how PETEY fits on your desktop.",
         summary="Theme, display, window & your name", icon="◐", group="Your companion",
         save_hint="Theme and window changes save automatically. Your name has its own Save button."),
    dict(id="personality", title="Personality & voice", description="Shape PETEY’s character, conversation style, and spoken voice.",
         summary="Character, speaking & saved personas", icon="✧", group="Your companion",
         save_hint="Use Save personality & voice to save character, style, and voice together."),
    dict(id="microphone", title="Microphone", description="Choose how you speak to PETEY and test your audio input.",
         summary="Listening mode, input device & testing", icon="⌁", group="Your companion",
         save_hint="Use Save microphone settings to apply changes to every personality."),
    dict(id="providers", title="Models & API keys", description="Connect services and choose the models behind each capability.",
         summary="API keys, chat, speech & search models", icon="◇", group="Connections",
         save_hint="Each service has its own Save button. Saving a key keeps the other saved keys."),
    dict(id="tools", title="Tools & integrations", description="Manage the capabilities PETEY can use during a conversation.",
         summary="Approved folders, MCP & add-ons", icon="⌘", group="Connections",
         save_hint="Connection switches apply immediately. Add-on changes require a restart."),
    dict(id="knowledge", title="Knowledge files", description="Add reference material and check what PETEY can find.",
         summary="Upload, manage & search reference files", icon="▤", group="Your data",
         save_hint="Uploads and file deletions apply immediately."),
    dict(id="memory", title="Memory & privacy", description="Review local storage and control the data PETEY keeps.",
         summary="Stored conversations & data removal", icon="◷", group="Your data",
         save_hint="Data removal requires confirmation and cannot be undone."),
)
