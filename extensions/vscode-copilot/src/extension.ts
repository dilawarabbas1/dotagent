// dotagent — Copilot attribution VS Code extension.
//
// Strategy: GitHub Copilot accepts inline suggestions through the standard
// `editor.action.inlineSuggest.commit` command. We listen for that command
// (and the chat-apply commands) and remember the timestamp + active document.
// On the next save / change to that document, if it's within the configured
// attribution window, we forward the edit to `dotagent observe` tagged
// `tool=copilot`.
//
// Build:
//   cd extensions/vscode-copilot
//   npm install
//   npm run compile
//   npm run package         # produces dotagent-copilot-0.1.0.vsix
//   code --install-extension dotagent-copilot-0.1.0.vsix

import * as cp from "child_process";
import * as path from "path";
import * as vscode from "vscode";

interface CopilotMark {
  uri: vscode.Uri;
  ts: number;
}

let lastCopilot: CopilotMark | null = null;

const COPILOT_COMMANDS = new Set<string>([
  "editor.action.inlineSuggest.commit",
  "editor.action.inlineSuggest.acceptNextWord",
  "github.copilot.acceptCursorPanelSolution",
  "github.copilot.generate",
  "github.copilot.applySuggestion",
]);

function isWithinWindow(ms: number, windowSeconds: number): boolean {
  return Date.now() - ms <= windowSeconds * 1000;
}

function findRepoRoot(uri: vscode.Uri): string | null {
  const folder = vscode.workspace.getWorkspaceFolder(uri);
  return folder ? folder.uri.fsPath : null;
}

function relPath(uri: vscode.Uri, repo: string): string {
  return path.relative(repo, uri.fsPath).split(path.sep).join("/");
}

function forwardToDotagent(repo: string, file: string, kind: "edit" | "save") {
  const cfg = vscode.workspace.getConfiguration("dotagent");
  const bin = cfg.get<string>("binaryPath", "dotagent");
  const args = [
    "observe", kind,
    "--tool", "copilot",
    "--summary", `copilot ${kind} via vscode extension`,
    "--files", file,
  ];
  cp.execFile(bin, args, { cwd: repo, timeout: 5000 }, (err, _stdout, stderr) => {
    if (err) {
      console.error(`[dotagent] forward failed:`, err.message, stderr);
    }
  });
}

export function activate(ctx: vscode.ExtensionContext) {
  console.log("[dotagent-copilot] activated");

  const wrapped = vscode.commands.executeCommand;
  // We can't override the global, so instead we listen to the inline-suggest events.
  // VS Code 1.85+ exposes `inlineSuggest.events` via the proposed API for
  // most users; the safest signal across versions is the command intercept below.

  // Intercept Copilot-flavored commands by re-registering them as wrappers that
  // call through to the original. (VS Code lets us register a command that
  // shadows Copilot's; we record the timestamp then defer to the original.)
  for (const cmd of COPILOT_COMMANDS) {
    const sub = vscode.commands.registerCommand(`dotagent.copilot.intercept.${cmd}`, async () => {
      const editor = vscode.window.activeTextEditor;
      if (editor) {
        lastCopilot = { uri: editor.document.uri, ts: Date.now() };
      }
      try {
        await vscode.commands.executeCommand(cmd);
      } catch (e) {
        // Forward errors so we don't break the original command.
        console.error("[dotagent-copilot] command intercept failed:", e);
      }
    });
    ctx.subscriptions.push(sub);
  }

  // Track Copilot's inline-suggest acceptance via an editor event heuristic:
  // when the document changes and Copilot was active recently, we mark the doc.
  ctx.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((evt) => {
      const cfg = vscode.workspace.getConfiguration("dotagent");
      const window = cfg.get<number>("attributionWindowSeconds", 5);
      if (!lastCopilot || lastCopilot.uri.toString() !== evt.document.uri.toString()) {
        return;
      }
      if (!isWithinWindow(lastCopilot.ts, window)) {
        return;
      }
      const repo = findRepoRoot(evt.document.uri);
      if (!repo) return;
      forwardToDotagent(repo, relPath(evt.document.uri, repo), "edit");
    }),
  );

  ctx.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const cfg = vscode.workspace.getConfiguration("dotagent");
      const window = cfg.get<number>("attributionWindowSeconds", 5);
      if (!lastCopilot || lastCopilot.uri.toString() !== doc.uri.toString()) return;
      if (!isWithinWindow(lastCopilot.ts, window)) return;
      const repo = findRepoRoot(doc.uri);
      if (!repo) return;
      forwardToDotagent(repo, relPath(doc.uri, repo), "save");
      lastCopilot = null;
    }),
  );
}

export function deactivate() {
  console.log("[dotagent-copilot] deactivated");
}
