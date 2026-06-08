import * as vscode from "vscode";
import * as http from "http";

interface SearchResultItem {
  chunk_id: string;
  file_path: string;
  node_path: string;
  node_type: string;
  signature: string;
  source_text: string;
  score: number;
}

interface SearchApiResponse {
  results: SearchResultItem[];
  count: number;
  query: string;
}

export class SearchProvider {
  private port: number;

  constructor(port: number) {
    this.port = port;
  }

  async showSearchPanel(): Promise<void> {
    const query = await vscode.window.showInputBox({
      prompt: "Search your codebase semantically...",
      placeHolder: "Search your codebase semantically...",
    });

    if (!query) {
      return;
    }

    try {
      const data = await this.fetchSearchResults(query);
      this.displayResults(query, data);
    } catch (error) {
      vscode.window.showErrorMessage(
        `CodeSage: API not reachable at localhost:${this.port}. Is the server running?`
      );
    }
  }

  private fetchSearchResults(query: string): Promise<SearchApiResponse> {
    return new Promise((resolve, reject) => {
      const encodedQuery = encodeURIComponent(query);
      const url = `http://localhost:${this.port}/search?q=${encodedQuery}&top_k=10`;

      http
        .get(url, (res) => {
          let body = "";
          res.on("data", (chunk: Buffer) => {
            body += chunk.toString();
          });
          res.on("end", () => {
            try {
              const data = JSON.parse(body) as SearchApiResponse;
              resolve(data);
            } catch {
              reject(new Error("Failed to parse API response"));
            }
          });
        })
        .on("error", (err: Error) => {
          reject(err);
        });
    });
  }

  private displayResults(query: string, data: SearchApiResponse): void {
    const panel = vscode.window.createWebviewPanel(
      "codesageSearch",
      "CodeSage Search Results",
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
      }
    );

    // Sort results by score descending
    const sortedResults = [...data.results].sort((a, b) => b.score - a.score);

    const resultsHtml = sortedResults
      .map(
        (r) => `
        <div class="result-card" data-file="${this.escapeHtml(r.file_path)}">
          <div class="node-path">${this.escapeHtml(r.node_path)}</div>
          <div class="file-path">${this.escapeHtml(r.file_path)}</div>
          <div class="score">Score: ${r.score.toFixed(2)}</div>
          <code class="signature">${this.escapeHtml(r.signature)}</code>
        </div>
      `
      )
      .join("");

    panel.webview.html = `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CodeSage Search Results</title>
        <style>
          body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background: var(--vscode-editor-background);
            padding: 16px;
            margin: 0;
          }
          h2 {
            color: var(--vscode-textLink-foreground);
            margin-bottom: 16px;
            font-size: 14px;
          }
          .result-card {
            border: 1px solid var(--vscode-panel-border);
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: background 0.15s;
          }
          .result-card:hover {
            background: var(--vscode-list-hoverBackground);
          }
          .node-path {
            font-weight: bold;
            font-size: 13px;
            color: var(--vscode-symbolIcon-functionForeground);
          }
          .file-path {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            margin-top: 4px;
          }
          .score {
            font-size: 11px;
            color: var(--vscode-textLink-foreground);
            margin-top: 4px;
          }
          .signature {
            display: block;
            margin-top: 8px;
            padding: 8px;
            background: var(--vscode-textCodeBlock-background);
            border-radius: 4px;
            font-size: 12px;
            white-space: pre-wrap;
            font-family: var(--vscode-editor-font-family);
          }
          .empty {
            color: var(--vscode-descriptionForeground);
            font-style: italic;
          }
        </style>
      </head>
      <body>
        <h2>Results for: "${this.escapeHtml(query)}" (${data.count} found)</h2>
        ${
          sortedResults.length === 0
            ? '<p class="empty">No results found.</p>'
            : resultsHtml
        }
        <script>
          const vscode = acquireVsCodeApi();
          document.querySelectorAll('.result-card').forEach(card => {
            card.addEventListener('click', () => {
              const filePath = card.getAttribute('data-file');
              vscode.postMessage({ command: 'openFile', filePath });
            });
          });
        </script>
      </body>
      </html>
    `;

    // Handle messages from the webview
    panel.webview.onDidReceiveMessage(
      (message) => {
        if (message.command === "openFile" && message.filePath) {
          const uri = vscode.Uri.file(message.filePath);
          vscode.window.showTextDocument(uri);
        }
      },
      undefined,
      []
    );
  }

  private escapeHtml(text: string): string {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
}
