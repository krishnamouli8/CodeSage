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

export class CodeSageHoverProvider implements vscode.HoverProvider {
  private port: number;

  constructor(port: number) {
    this.port = port;
  }

  async provideHover(
    document: vscode.TextDocument,
    position: vscode.Position,
    _token: vscode.CancellationToken
  ): Promise<vscode.Hover | undefined> {
    const wordRange = document.getWordRangeAtPosition(position);
    if (!wordRange) {
      return undefined;
    }

    const word = document.getText(wordRange);
    if (!word || word.length < 2) {
      return undefined;
    }

    try {
      const data = await this.fetchSearch(word);

      if (data.results.length === 0) {
        return undefined;
      }

      const topResult = data.results[0];

      // Only show hover if the node_path matches the hovered word (case-insensitive)
      const nodeParts = topResult.node_path.split(".");
      const lastPart = nodeParts[nodeParts.length - 1];

      if (lastPart.toLowerCase() !== word.toLowerCase()) {
        return undefined;
      }

      // Build hover content
      const markdown = new vscode.MarkdownString();
      markdown.appendMarkdown(`**${topResult.node_path}**\n\n`);
      markdown.appendCodeblock(topResult.signature, "python");

      if (topResult.source_text) {
        // Show first few lines as a preview
        const preview = topResult.source_text.split("\n").slice(0, 5).join("\n");
        markdown.appendMarkdown("\n\n---\n\n");
        markdown.appendCodeblock(preview, "python");
      }

      return new vscode.Hover(markdown, wordRange);
    } catch {
      // API unreachable — silently return undefined (no hover)
      return undefined;
    }
  }

  private fetchSearch(query: string): Promise<SearchApiResponse> {
    return new Promise((resolve, reject) => {
      const encodedQuery = encodeURIComponent(query);
      const url = `http://localhost:${this.port}/search?q=${encodedQuery}&top_k=1`;

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
}
