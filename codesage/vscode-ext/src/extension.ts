import * as vscode from "vscode";
import { SearchProvider } from "./searchProvider";
import { CodeSageHoverProvider } from "./hoverProvider";

let searchProvider: SearchProvider;

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration("codesage");
  const port = config.get<number>("apiPort", 8000);

  searchProvider = new SearchProvider(port);

  // Register the search command
  const searchCommand = vscode.commands.registerCommand(
    "codesage.search",
    () => {
      searchProvider.showSearchPanel();
    }
  );
  context.subscriptions.push(searchCommand);

  // Register hover provider for Python and Java
  const hoverProvider = new CodeSageHoverProvider(port);

  context.subscriptions.push(
    vscode.languages.registerHoverProvider(
      { scheme: "file", language: "python" },
      hoverProvider
    )
  );
  context.subscriptions.push(
    vscode.languages.registerHoverProvider(
      { scheme: "file", language: "java" },
      hoverProvider
    )
  );
}

export function deactivate() {
  // Nothing to clean up
}
