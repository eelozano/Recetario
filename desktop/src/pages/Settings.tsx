/**
 * Settings — paused for Architecture v2.
 *
 * The old panel wrote a bring-your-own Anthropic key to ~/.recetario/.env for
 * the localhost backend to read. That backend was removed in step 3, so there's
 * nothing to configure yet. Settings returns in a later step as a local
 * config.json (data-folder picker + the API key for the on-demand recipe-import
 * helper) — see docs/architecture-v2-proposal.md §7.
 */
export function Settings() {
  return (
    <div className="settings">
      <h2>Settings</h2>
      <p className="muted settings__intro">
        Settings are paused while Recetario moves to its local-first file store.
        They'll return in a later step with a data-folder picker and the API key
        for on-demand recipe import. Your recipes, meal calendar, and shopping
        lists work without any configuration.
      </p>
    </div>
  );
}
