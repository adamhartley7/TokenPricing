# B — build
Model: deepseek-v4-pro | Provider: deepseek
Tokens: 461+4096 | Cost: $0.003764 | Duration: 46.85s

I'll produce a set of ready-to-save files that implement the full Cowork tab system—provider abstraction, file sandbox with confirmation, agent harness, and UI—integrated into the existing 7C's app structure.

```text
src/shared/gateway.ts
```
```ts
/**
 * Mock of the existing shared LLM gateway.
 * In the real codebase this already handles spend-guard rate limiting,
 * token counting, and real‑time cost tracking for Chat and Code tabs.
 */
export interface LLMCompletionOptions {
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number;
  maxTokens?: number;
}

export interface LLMCompletionResult {
  content: string;
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    cost: number;
  };
}

export interface LLMGateway {
  complete(options: LLMCompletionOptions): Promise<LLMCompletionResult>;
  countTokens(text: string, model: string): Promise<number>;
  // Additional methods for streaming exist but are omitted for brevity.
}

// Injected global instance – already created by the main app setup
export const sharedGateway: LLMGateway = {
  async complete(opts) {
    // Real implementation calls OpenAI/Anthropic with rate limiting and spend guard
    return {
      content: `Mock response for model ${opts.model}`,
      usage: {
        promptTokens: Math.ceil(opts.messages.reduce((s, m) => s + m.content.length, 0) / 4),
        completionTokens: 50,
        totalTokens: 0,
        cost: 0.0001,
      },
    };
  },
  async countTokens(text, model) {
    return Math.ceil(text.length / 4);
  },
};
```

```text
src/agent/providers/AgentLLMProvider.ts
```
```ts
/**
 * Uniform provider abstraction consumed by the agent harness.
 * It decouples the agent loop from any concrete LLM backend,
 * reusing the existing gateway for token counting and cost.
 */
export interface AgentLLMProvider {
  /** Sends a chat completion request. Returns content and usage metadata. */
  complete(
    messages: Array<{ role: string; content: string }>,
    options?: {
      model?: string;
      temperature?: number;
      maxTokens?: number;
    }
  ): Promise<{ content: string; usage: { totalTokens: number; cost: number } }>;

  /** Estimates token count for a given string, used for budget checks. */
  countTokens(text: string): Promise<number>;

  /** Current budget remaining (in dollars). Implementation may query the spend guard. */
  getRemainingBudget(): number;
}
```

```text
src/agent/providers/GatewayProviderAdapter.ts
```
```ts
import { sharedGateway, LLMGateway } from '../../shared/gateway';
import { AgentLLMProvider } from './AgentLLMProvider';

/**
 * Adapter that wraps the existing LLMGateway into the AgentLLMProvider.
 * Adds a simple budget tracking; in production the gateway would expose
 * a spend‑guard service that we query directly.
 */
export class GatewayProviderAdapter implements AgentLLMProvider {
  private gateway: LLMGateway;
  private budgetLimit: number;
  private totalSpent: number = 0;

  constructor(gateway?: LLMGateway, budgetLimit: number = 1.0) {
    this.gateway = gateway ?? sharedGateway;
    this.budgetLimit = budgetLimit;
  }

  async complete(
    messages: Array<{ role: string; content: string }>,
    options?: { model?: string; temperature?: number; maxTokens?: number }
  ) {
    const result = await this.gateway.complete({
      model: options?.model ?? 'gpt-4o',
      messages,
      temperature: options?.temperature,
      maxTokens: options?.maxTokens,
    });
    this.totalSpent += result.usage.cost;
    return {
      content: result.content,
      usage: {
        totalTokens: result.usage.totalTokens,
        cost: result.usage.cost,
      },
    };
  }

  async countTokens(text: string): Promise<number> {
    // The gateway already supports token counting.
    return this.gateway.countTokens(text, 'gpt-4o');
  }

  getRemainingBudget(): number {
    return Math.max(0, this.budgetLimit - this.totalSpent);
  }
}
```

```text
src/agent/fileSandbox/FileAccessManager.ts
```
```ts
import fs from 'fs/promises';
import path from 'path';
import { EventEmitter } from 'events';

type FileAction = 'read' | 'write' | 'delete' | 'rename' | 'move';

export interface FileOperationRequest {
  id: string;
  action: FileAction;
  filePath: string;
  newPath?: string; // for rename/move
  content?: string; // for write
}

/**
 * Middleware that enforces allowlisted directories and gates
 * destructive operations behind mandatory user confirmation.
 * All file system interactions required by agent tools pass through here.
 */
export class FileAccessManager extends EventEmitter {
  private allowedRoots: string[];
  private pendingOps: Map<string, { request: FileOperationRequest; resolve: (approved: boolean) => void }> = new Map();
  private opCounter = 0;

  constructor(allowedRoots: string[]) {
    super();
    // Normalize paths
    this.allowedRoots = allowedRoots.map(p => path.resolve(p));
  }

  /**
   * Check whether a path is within the allowed directories.
   */
  isPathAllowed(targetPath: string): boolean {
    const resolved = path.resolve(targetPath);
    return this.allowedRoots.some(root => resolved.startsWith(root + path.sep) || resolved === root);
  }

  /**
   * Perform a read operation (allowed without confirmation).
   */
  async readFile(filePath: string): Promise<string> {
    if (!this.isPathAllowed(filePath)) {
      throw new Error(`Access denied: ${filePath} is not in allowed directories.`);
    }
    return fs.readFile(filePath, 'utf-8');
  }

  /**
   * Execute a destructive operation – returns a Promise that resolves after user approval.
   */
  private requestConfirmation(request: FileOperationRequest): Promise<boolean> {
    const id = String(++this.opCounter);
    request.id = id;
    return new Promise<boolean>((resolve) => {
      this.pendingOps.set(id, { request, resolve });
      this.emit('confirmation-required', request);
    });
  }

  /**
   * Called by the UI when the user confirms or rejects a pending operation.
   */
  approveOperation(requestId: string, approved: boolean): void {
    const pending = this.pendingOps.get(requestId);
    if (pending) {
      this.pendingOps.delete(requestId);
      pending.resolve(approved);
    }
  }

  /**
   * Write a file if allowed and confirmed.
   */
  async writeFile(filePath: string, content: string): Promise<void> {
    if (!this.isPathAllowed(filePath)) throw new Error(`Access denied: ${filePath}`);
    const request: FileOperationRequest = { action: 'write', filePath, content };
    const approved = await this.requestConfirmation(request);
    if (!approved) throw new Error('User denied file write');
    await fs.writeFile(filePath, content, 'utf-8');
  }

  /**
   * Delete a file if allowed and confirmed.
   */
  async deleteFile(filePath: string): Promise<void> {
    if (!this.isPathAllowed(filePath)) throw new Error(`Access denied: ${filePath}`);
    const request: FileOperationRequest = { action: 'delete', filePath };
    const approved = await this.requestConfirmation(request);
    if (!approved) throw new Error('User denied file deletion');
    await fs.unlink(filePath);
  }

  /**
   * Rename a file (destructive) if allowed and confirmed.
   */
  async renameFile(oldPath: string, newPath: string): Promise<void> {
    if (!this.isPathAllowed(oldPath) || !this.isPathAllowed(newPath)) {
      throw new Error(`Access denied: paths must be within allowed directories.`);
    }
    const request: FileOperationRequest = { action: 'rename', filePath: oldPath, newPath };
    const approved = await this.requestConfirmation(request);
    if (!approved) throw new Error('User denied rename');
    await fs.rename(oldPath, newPath);
  }

  /**
   * Move a file (alias for rename) with the same restriction.
   */
  async moveFile(oldPath: string, newPath: string): Promise<void> {
    return this.renameFile(oldPath, newPath);
  }
}
```

```text
src/agent/harness/Tools.ts
```
```ts
import { FileAccessManager } from '../fileSandbox/FileAccessManager';
import { AgentLLMProvider } from '../providers/AgentLLMProvider';

/**
 * Tool definitions that the agent loop can invoke.
 * Every tool receives the sandbox and provider, and returns a tool-specific result.
 */
export interface ToolCall {
  name: string;
  parameters: Record<string, any>;
}

export interface ToolResult {
  output: string;
  metadata?: Record<string, any>;
}

export class ToolExecutor {
  constructor(
    private sandbox: FileAccessManager,
    private provider: AgentLLMProvider,
    // Optionally inject the Code tab executor
    private codeExecutor?: (code: string, workingDir: string) => Promise<string>
  ) {}

  async execute(tool: ToolCall): Promise<ToolResult> {
    switch (tool.name) {
      case 'readFile': {
        const content = await this.sandbox.readFile(tool.parameters.path);
        return { output: content };
      }
      case 'writeFile': {
        await this.sandbox.writeFile(tool.parameters.path, tool.parameters.content);
        return { output: `File written: ${tool.parameters.path}` };
      }
      case 'deleteFile': {
        await this.sandbox.deleteFile(tool.parameters.path);
        return { output: `File deleted: ${tool.parameters.path}` };
      }
      case 'renameFile': {
        await this.sandbox.renameFile(tool.parameters.oldPath, tool.parameters.newPath);
        return { output: `Renamed ${tool.parameters.oldPath} => ${tool.parameters.newPath}` };
      }
      case 'moveFile': {
        await this.sandbox.moveFile(tool.parameters.oldPath, tool.parameters.newPath);
        return { output: `Moved ${tool.parameters.oldPath} => ${tool.parameters.newPath}` };
      }
      case 'listDirectory': {
        // For now, just a stub – could be extended
        return { output: `Directory listing not yet implemented.` };
      }
      case 'executeCode': {
        if (!this.codeExecutor) {
          throw new Error('Code execution not available');
        }
        const workingDir = tool.parameters.workingDir || '/tmp';
        if (!this.sandbox.isPathAllowed(workingDir)) {
          throw new Error(`Working directory ${workingDir} not allowed`);
        }
        const result = await this.codeExecutor(tool.parameters.code, workingDir);
        return { output: result };
      }
      default:
        throw new Error(`Unknown tool: ${tool.name}`);
    }
  }
}
```

```text
src/agent/harness/AgentHarness.ts
```
```ts
import { AgentLLMProvider } from '../providers/AgentLLMProvider';
import { ToolExecutor, ToolCall, ToolResult } from './Tools';

export interface AgentStep {
  type: 'thought' | 'tool_call' | 'tool_result' | 'user_confirmation' | 'error' | 'complete';
  content: string;
  toolCall?: ToolCall;
  toolResult?: ToolResult;
  confirmationRequest?: any; // Will hold FileOperationRequest
  cost: number;
  remainingBudget: number;
}

/**
 * Multi‑step agent loop that decomposes a task, selects tools,
 * performs scoped file operations, and iterates until completion.
 * It uses an async generator to yield steps to the UI in real time.
 */
export class AgentHarness {
  constructor(
    private provider: AgentLLMProvider,
    private toolExecutor: ToolExecutor,
    private systemPrompt: string = ''
  ) {}

  async *run(task: string, maxSteps: number = 20): Async