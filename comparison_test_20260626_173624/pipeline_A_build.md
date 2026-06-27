# A — build
Model: deepseek-v4-pro | Provider: deepseek
Tokens: 688+4096 | Cost: $0.003863 | Duration: 50.41s

```ts
// src/cowork/agent/toolInterface.ts
import { z } from 'zod';

export const ReadFileInput = z.object({
  filePath: z.string().describe('Absolute or relative path from allowed root'),
});

export const WriteFileInput = z.object({
  filePath: z.string(),
  content: z.string(),
});

export const ListDirInput = z.object({
  dirPath: z.string().describe('Directory to list'),
});

export const RunCommandInput = z.object({
  command: z.string().describe('Shell command to run'),
  workingDir: z.string().optional().describe('Working directory within allowed root'),
});

export const SearchInput = z.object({
  pattern: z.string().describe('Regex or glob'),
  rootPath: z.string().describe('Search root'),
});

export const ToolSchemas = {
  read_file: { input: ReadFileInput, description: 'Read file contents' },
  write_file: { input: WriteFileInput, description: 'Create or overwrite a file' },
  list_dir: { input: ListDirInput, description: 'List directory entries' },
  run_command: { input: RunCommandInput, description: 'Execute a shell command' },
  search: { input: SearchInput, description: 'Search files by pattern' },
} as const;

export type ToolName = keyof typeof ToolSchemas;
export type ToolInput<T extends ToolName> = z.infer<(typeof ToolSchemas)[T]['input']>;

export interface ToolCall {
  id: string;
  name: ToolName;
  arguments: Record<string, unknown>;
}

export interface ToolResult {
  id: string;
  name: ToolName;
  output: unknown;
  error?: string;
}

export interface ActionDescription {
  thought?: string;
  toolCalls: ToolCall[];
}
```

```ts
// src/cowork/security/allowlist.ts
import path from 'path';
import fs from 'fs/promises';
import { createHash } from 'crypto';

interface AllowlistEntry {
  workspaceId: string;
  root: string;     // absolute, real path
  read: boolean;
  write: boolean;
  exec: boolean;
}

const allowlist: Map<string, AllowlistEntry> = new Map();

/**
 * Register a workspace root directory with permissions.
 */
export function registerWorkspace(
  workspaceId: string,
  root: string,
  permissions: { read: boolean; write: boolean; exec: boolean }
): void {
  const resolved = path.resolve(root);
  allowlist.set(workspaceId, {
    workspaceId,
    root: resolved,
    ...permissions,
  });
}

/**
 * Resolve a requested path to an safe absolute path inside the workspace root.
 * Rejects if the path escapes the root or the operation is not allowed.
 */
export async function resolveAllowedPath(
  workspaceId: string,
  requestedPath: string,
  operation: 'read' | 'write' | 'exec'
): Promise<string> {
  const entry = allowlist.get(workspaceId);
  if (!entry) throw new Error(`Workspace ${workspaceId} not allowlisted`);

  if (!entry[operation]) {
    throw new Error(`Operation ${operation} not allowed for workspace ${workspaceId}`);
  }

  // Join with root and resolve to real path
  const candidate = path.resolve(entry.root, requestedPath);
  // Use realpath to resolve symlinks
  let real: string;
  try {
    real = await fs.realpath(candidate);
  } catch {
    // If file doesn't exist yet, we can still allow (for write) but we ensure parent is real
    if (operation === 'write') {
      const parent = path.resolve(entry.root, path.dirname(requestedPath));
      try {
        const parentReal = await fs.realpath(parent);
        if (!parentReal.startsWith(entry.root + path.sep) && parentReal !== entry.root) {
          throw new Error('Parent directory escapes workspace root');
        }
        return candidate; // will be created later
      } catch {
        throw new Error('Parent directory does not exist or access denied');
      }
    }
    throw new Error('File not found and not a write operation');
  }

  // Check if real path is inside the root
  if (!real.startsWith(entry.root + path.sep) && real !== entry.root) {
    throw new Error('Path escapes workspace root');
  }

  // Additional traversal check: no '..' segments after normalization
  // With realpath this is already handled, but keep a sanity check
  const relative = path.relative(entry.root, real);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    throw new Error('Path traversal detected');
  }

  return real;
}

/**
 * Compute file hash (MD5) for audit.
 */
export async function fileHash(filePath: string): Promise<string> {
  try {
    const data = await fs.readFile(filePath);
    return createHash('md5').update(data).digest('hex');
  } catch {
    return 'none';
  }
}
```

```ts
// src/cowork/security/operationClassifier.ts
export type OperationType = 'read_file' | 'list_dir' | 'search' | 'write_file' | 'run_command';

const SAFE_OPS: Set<OperationType> = new Set(['read_file', 'list_dir', 'search']);
const DESTRUCTIVE_OPS: Set<OperationType> = new Set(['write_file', 'run_command']);

export function isDestructive(op: OperationType): boolean {
  return DESTRUCTIVE_OPS.has(op);
}

export function isSafe(op: OperationType): boolean {
  return SAFE_OPS.has(op);
}
```

```ts
// src/cowork/security/confirmationManager.ts
import { EventEmitter } from 'events';

export interface ConfirmationRequest {
  id: string;
  type: 'destructive';
  operation: string;
  details: string;
  onConfirm: () => void;
  onReject: () => void;
}

class ConfirmationManager extends EventEmitter {
  private pending: Map<string, ConfirmationRequest> = new Map();

  requestConfirmation(op: string, details: string): Promise<void> {
    const id = Math.random().toString(36).slice(2);
    return new Promise((resolve, reject) => {
      const req: ConfirmationRequest = {
        id,
        type: 'destructive',
        operation: op,
        details,
        onConfirm: () => {
          this.pending.delete(id);
          resolve();
        },
        onReject: () => {
          this.pending.delete(id);
          reject(new Error('User rejected destructive operation'));
        },
      };
      this.pending.set(id, req);
      this.emit('new-request', req);
    });
  }

  confirm(id: string): void {
    const req = this.pending.get(id);
    if (req) req.onConfirm();
  }

  reject(id: string): void {
    const req = this.pending.get(id);
    if (req) req.onReject();
  }

  getPending(): ConfirmationRequest[] {
    return Array.from(this.pending.values());
  }
}

export const confirmationManager = new ConfirmationManager();
```

```ts
// src/cowork/security/auditLog.ts
export interface AuditEntry {
  timestamp: number;
  workspaceId: string;
  operation: string;
  path: string;
  beforeHash?: string;
  afterHash?: string;
}

const log: AuditEntry[] = [];

export function addAuditEntry(entry: AuditEntry): void {
  log.push(entry);
  // Optionally emit event for UI
}

export function getAuditLog(): readonly AuditEntry[] {
  return log;
}
```

```ts
// src/cowork/agent/toolExecutor.ts
import { ToolSchemas, ToolCall, ToolResult } from './toolInterface';
import { resolveAllowedPath, fileHash } from '../security/allowlist';
import { confirmationManager } from '../security/confirmationManager';
import { isDestructive } from '../security/operationClassifier';
import { addAuditEntry } from '../security/auditLog';
import fs from 'fs/promises';
import path from 'path';
import { exec as execCb } from 'child_process';
import { promisify } from 'util';
const execAsync = promisify(execCb);

export async function executeTool(
  workspaceId: string,
  toolCall: ToolCall
): Promise<ToolResult> {
  const { name, arguments: args } = toolCall;
  const schema = ToolSchemas[name];
  if (!schema) throw new Error(`Unknown tool: ${name}`);
  const input = schema.input.parse(args);

  // For destructive ops, get user confirmation
  if (isDestructive(name)) {
    const details = JSON.stringify(input, null, 2);
    await confirmationManager.requestConfirmation(name, details);
  }

  let resolvedPath = '';
  switch (name) {
    case 'read_file': {
      const { filePath } = input;
      resolvedPath = await resolveAllowedPath(workspaceId, filePath, 'read');
      const content = await fs.readFile(resolvedPath, 'utf-8');
      const beforeHash = await fileHash(resolvedPath);
      addAuditEntry({
        timestamp: Date.now(),
        workspaceId,
        operation: 'read_file',
        path: resolvedPath,
        beforeHash,
      });
      return { id: toolCall.id, name, output: content };
    }
    case 'write_file': {
      const { filePath, content } = input;
      resolvedPath = await resolveAllowedPath(workspaceId, filePath, 'write');
      const beforeHash = await fileHash(resolvedPath);
      await fs.mkdir(path.dirname(resolvedPath), {