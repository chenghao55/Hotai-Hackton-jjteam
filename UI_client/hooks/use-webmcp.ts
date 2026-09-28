'use client';

import { useEffect } from 'react';

type ModelContext = {
  registerTool: (tool: {
    name: string;
    title?: string;
    description: string;
    inputSchema: object;
    annotations?: { readOnlyHint?: boolean; untrustedContentHint?: boolean };
    execute: (input: unknown) => unknown;
  }, options?: { signal?: AbortSignal }) => void | Promise<void>;
};

declare global {
  interface Document { modelContext?: ModelContext }
}

export function useCaseStatusTool(
  updateStatus: (caseId: string, status: string) => boolean,
) {
  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();

    void Promise.resolve(context.registerTool({
      name: 'update_case_status',
      title: '更新案件狀態',
      description: '更新目前營運案件的覆核或派工狀態，並同步更新畫面。',
      inputSchema: {
        type: 'object',
        properties: {
          caseId: { type: 'string' },
          status: { type: 'string', enum: ['待人工覆核', '待清潔', '待維修', '已結案'] },
        },
        required: ['caseId', 'status'],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute(input) {
        const value = input as { caseId?: unknown; status?: unknown };
        if (typeof value.caseId !== 'string' || typeof value.status !== 'string') {
          throw new Error('caseId 與 status 必須是字串');
        }
        const updated = updateStatus(value.caseId, value.status);
        if (!updated) throw new Error('找不到案件或狀態不合法');
        return { caseId: value.caseId, status: value.status, updated: true };
      },
    }, { signal: lifecycle.signal })).catch(() => undefined);

    return () => lifecycle.abort();
  }, [updateStatus]);
}
