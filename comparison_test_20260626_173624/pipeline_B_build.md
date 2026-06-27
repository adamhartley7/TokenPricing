# B — build
Model: deepseek-v4-pro | Provider: deepseek
Tokens: 675+4096 | Cost: $0.003857 | Duration: 56.75s

Below are the complete, ready‑to‑save files implementing the Cowork tab with scoped file access, multi‑step agent harness, spend‑guard integration, and destructive‑op confirmations.

**src/config/cowork.ts**
```ts
// Cowork tab configuration
export const coworkConfig = {
  // Maximum number of plan/execute steps the agent may take
  maxSteps: 10,
  // Comma-separated list of directories the agent is allowed to access
  allowedDirectories: process.env.ALLOWED_DIRS?.split(',') ?? ['/home/user/workspace'],
  // Providers that can be used by the Cowork tab (must match global providers)
  availableProviders: ['openai', 'anthropic'] as const,
  // Default model to use for planning
  defaultModel: 'gpt-4-turbo',
};
```

**src/lib/types/cowork.ts**
```ts
// Shared types for Cowork tab

export type ToolName = 'readFile' | 'writeFile' | 'deleteFile' | 'listDir' | 'searchCode';

export interface ToolCall {
  name: ToolName;
  args: Record<string, unknown>;
  // Some tools require user confirmation before execution
  requiresConfirmation?: boolean;
  confirmationMessage?: string;
  confirmationId?: string; // set by engine when awaiting approval
}

export interface ToolResult {
  success: boolean;
  output: string;
  error?: string;
}

export interface StepState {
  index: number;
  status: 'pending' | 'running' | 'completed' | 'error' | 'awaiting_confirmation';
  description: string;
  toolCalls?: ToolCall[];
  results?: ToolResult[];
  confirmationRequested?: ConfirmationRequest;
  startTime: number;
  endTime?: number;
}

export interface ConfirmationRequest {
  confirmationId: string;
  message: string;
  toolCall: ToolCall;
}

export type AgentStatus = 'idle' | 'running' | 'awaiting_confirmation' | 'completed' | 'error' | 'aborted';

export interface CoworkSession {
  sessionId: string;
  prompt: string;
  steps: StepState[];
  currentStep?: StepState;
  status: AgentStatus;
  error?: string;
  finalResult?: string;
  totalCost: number; // accumulated API cost
  createdAt: number;
  updatedAt: number;
}

// API payloads
export interface StartAgentRequest {
  prompt: string;
}

export interface ContinueAgentRequest {
  sessionId: string;
  action?: 'approve' | 'deny';
  confirmationId?: string;
  modification?: string; // optional modified args after user approval
}

export interface AgentResponse {
  session: CoworkSession;
}
```

**src/lib/agent/scopedFS.ts**
```ts
import { coworkConfig } from '@/config/cowork';
import path from 'path';

export interface FileSystem {
  readFile(filePath: string): Promise<string>;
  writeFile(filePath: string, content: string): Promise<void>;
  deleteFile(filePath: string): Promise<void>;
  listDirectory(dirPath: string): Promise<string[]>;
  exists(filePath: string): Promise<boolean>;
  isDirectory(filePath: string): Promise<boolean>;
  resolveAbsolute(filePath: string): string;
}

/**
 * Wraps any FileSystem implementation and restricts access
 * to a configurable list of allowed directories.
 */
export class ScopedFileSystem implements FileSystem {
  private allowedDirs: string[];
  private inner: FileSystem;

  constructor(inner: FileSystem, allowedDirectories?: string[]) {
    this.inner = inner;
    this.allowedDirs = (allowedDirectories ?? coworkConfig.allowedDirectories).map(d => path.resolve(d));
  }

  private validatePath(filePath: string, operation: string): void {
    const resolved = this.inner.resolveAbsolute(filePath);
    const isAllowed = this.allowedDirs.some(dir => resolved.startsWith(dir + path.sep) || resolved === dir);
    if (!isAllowed) {
      throw new Error(`Scoped access: ${operation} on "${filePath}" is outside allowed directories.`);
    }
  }

  async readFile(filePath: string): Promise<string> {
    this.validatePath(filePath, 'readFile');
    return this.inner.readFile(filePath);
  }

  async writeFile(filePath: string, content: string): Promise<void> {
    this.validatePath(filePath, 'writeFile');
    return this.inner.writeFile(filePath, content);
  }

  async deleteFile(filePath: string): Promise<void> {
    this.validatePath(filePath, 'deleteFile');
    return this.inner.deleteFile(filePath);
  }

  async listDirectory(dirPath: string): Promise<string[]> {
    this.validatePath(dirPath, 'listDir');
    return