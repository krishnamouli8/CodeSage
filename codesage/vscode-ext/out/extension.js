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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const searchProvider_1 = require("./searchProvider");
const hoverProvider_1 = require("./hoverProvider");
let searchProvider;
function activate(context) {
    const config = vscode.workspace.getConfiguration("codesage");
    const port = config.get("apiPort", 8000);
    searchProvider = new searchProvider_1.SearchProvider(port);
    // Register the search command
    const searchCommand = vscode.commands.registerCommand("codesage.search", () => {
        searchProvider.showSearchPanel();
    });
    context.subscriptions.push(searchCommand);
    // Register hover provider for Python and Java
    const hoverProvider = new hoverProvider_1.CodeSageHoverProvider(port);
    context.subscriptions.push(vscode.languages.registerHoverProvider({ scheme: "file", language: "python" }, hoverProvider));
    context.subscriptions.push(vscode.languages.registerHoverProvider({ scheme: "file", language: "java" }, hoverProvider));
}
function deactivate() {
    // Nothing to clean up
}
//# sourceMappingURL=extension.js.map