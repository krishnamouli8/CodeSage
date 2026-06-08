"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.CodeSageHoverProvider = void 0;
const vscode = __importStar(require("vscode"));
const http = __importStar(require("http"));
class CodeSageHoverProvider {
    constructor(port) {
        this.port = port;
    }
    async provideHover(document, position, _token) {
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
        }
        catch {
            // API unreachable — silently return undefined (no hover)
            return undefined;
        }
    }
    fetchSearch(query) {
        return new Promise((resolve, reject) => {
            const encodedQuery = encodeURIComponent(query);
            const url = `http://localhost:${this.port}/search?q=${encodedQuery}&top_k=1`;
            http
                .get(url, (res) => {
                let body = "";
                res.on("data", (chunk) => {
                    body += chunk.toString();
                });
                res.on("end", () => {
                    try {
                        const data = JSON.parse(body);
                        resolve(data);
                    }
                    catch {
                        reject(new Error("Failed to parse API response"));
                    }
                });
            })
                .on("error", (err) => {
                reject(err);
            });
        });
    }
}
exports.CodeSageHoverProvider = CodeSageHoverProvider;
//# sourceMappingURL=hoverProvider.js.map