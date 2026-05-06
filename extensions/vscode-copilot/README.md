# dotagent — Copilot attribution

A small VS Code extension that forwards GitHub Copilot edits into
`dotagent observe` so attribution survives in episodic memory.

## Build & install

```bash
cd extensions/vscode-copilot
npm install
npm run compile
npm run package        # produces dotagent-copilot-0.1.0.vsix
code --install-extension dotagent-copilot-0.1.0.vsix
```

## Settings

| Setting                                 | Default       | What it does                                                 |
| --------------------------------------- | ------------- | ------------------------------------------------------------ |
| `dotagent.binaryPath`                   | `"dotagent"`  | Path to the dotagent CLI on `$PATH`.                         |
| `dotagent.attributionWindowSeconds`     | `5`           | Edits within N seconds of a Copilot suggestion are tagged.   |

## How it decides "Copilot did this"

The extension listens for these signals, in order of confidence:

1. **Inline-suggest acceptance commands** (`editor.action.inlineSuggest.commit`,
   `github.copilot.acceptCursorPanelSolution`, etc.) — exposed as
   `dotagent.copilot.intercept.*` commands you can rebind to in keybindings.json.
2. **Document change within the attribution window after a Copilot command**
   fires `dotagent observe edit --tool copilot`.
3. **Save within the attribution window** fires `dotagent observe save --tool copilot`.

False positives are minimized by clearing the mark after each forwarded save.

## Limitations (be honest)

- Without intercepting the keybindings via `keybindings.json`, the activation
  signal depends on either the user manually rebinding to
  `dotagent.copilot.intercept.<command>` OR the VS Code Copilot extension
  cooperating. The fallback (timing window after any inline-suggest event)
  catches the common case but can miss edits that don't trigger a save within
  the window.
- This is an opt-in attribution layer, not a hard guarantee.
- The extension is not yet published to the VS Code Marketplace — install
  manually via the .vsix above.
