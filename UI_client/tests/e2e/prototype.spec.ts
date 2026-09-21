import { expect, test, type Page } from '@playwright/test';
import { analyses, nextStatus, type ScenarioKey } from '../../lib/prototype';

async function seedAnalysis(page: Page, scenario: ScenarioKey) {
  const result = analyses[scenario];
  const stored = {
    ...result,
    status: nextStatus(result.recommended_action),
    analyzed_at: '2026-09-16T02:30:00.000Z',
    source: 'mock-api',
  };
  await page.addInitScript(({ caseId, value }) => {
    sessionStorage.setItem(`capture-analysis:${caseId}`, value);
    sessionStorage.setItem('capture-analysis:latest', caseId);
  }, { caseId: result.case_id, value: JSON.stringify(stored) });
}

test('手機端可走到 AI 結果', async ({ page }) => {
  await page.goto('/capture/legacy');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /車尾右後方 45°/ }).click();
  await page.getByRole('button', { name: '疑似新車損' }).click();
  await page.getByRole('button', { name: /送出並即時檢查/ }).click();
  await expect(page.getByText('異常已安全回報')).toBeVisible();
  await expect(page.getByText('案件已送交營運人員覆核')).toBeVisible();
});

test('拍照規則可確認並進入空白相機頁後返回', async ({ page }) => {
  await page.goto('/capture');
  await page.waitForLoadState('networkidle');
  const confirmation = page.getByRole('checkbox', { name: '我已經詳細閱讀拍照規則及流程' });
  await expect(confirmation).not.toBeChecked();
  await expect(page.getByRole('button', { name: /開始拍照/ })).toBeDisabled();
  await confirmation.click();
  await expect(confirmation).not.toBeChecked();
  await expect(page.getByRole('alert')).toHaveText('請先詳細閱讀所有條款');
  await page.getByTestId('rules-scroll-area').evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    element.dispatchEvent(new Event('scroll', { bubbles: true }));
  });
  await confirmation.click();
  await expect(confirmation).toBeChecked();
  await expect(page.getByRole('link', { name: /開始拍照/ })).toBeEnabled();
  await page.getByRole('link', { name: /開始拍照/ }).click();
  await expect(page).toHaveURL(/\/capture\/camera$/);
  await expect(page.getByRole('heading', { name: /這次拍攝的是哪種車型/ })).toBeVisible();
  await page.getByRole('button', { name: /轎車/ }).click();
  await expect(page.getByRole('heading', { name: '加油卡與停車卡' })).toBeVisible();
  await expect(page.getByRole('button', { name: /開啟即時相機/ })).toBeVisible();
  await page.getByRole('link', { name: '返回拍照規則' }).click();
  await expect(page).toHaveURL(/\/capture$/);
});

test('正常分析結果完成還車且不需額外費用', async ({ page }) => {
  await seedAnalysis(page, 'normal');
  await page.goto('/capture/result');
  await expect(page.getByRole('heading', { name: '還車檢查已完成' })).toBeVisible();
  await expect(page.getByText(/本次不需支付額外費用/)).toBeVisible();
  await expect(page.getByRole('link', { name: /完成並返回首頁/ })).toBeVisible();
});

test('可選擇休旅車並逐張跳過八個基本拍攝步驟', async ({ page }) => {
  await page.goto('/capture/camera');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /休旅車/ }).click();
  for (let index = 0; index < 8; index += 1) {
    await page.getByRole('button', { name: '跳過此張' }).click();
  }
  await expect(page.getByRole('heading', { name: /是否有需要補拍的車損/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /新增損壞照片/ })).toBeVisible();
  await expect(page.getByText(/儲存 0 張照片/)).toBeVisible();
});

test('疑似車損可分別進入付款與人工覆核進度', async ({ page }) => {
  await seedAnalysis(page, 'damage');
  await page.goto('/capture/result');
  await expect(page.getByRole('heading', { name: 'AI 偵測到 2 處疑似問題' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '右後保桿出現疑似新增刮痕' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '右前車門下緣出現疑似新增凹痕' })).toBeVisible();
  await expect(page.getByText('NT$3,500–7,000')).toBeVisible();
  await expect(page.getByText('最終價格為：')).toBeVisible();
  await expect(page.getByText('NT$5,500')).toBeVisible();
  await page.getByRole('link', { name: /我對 AI 判讀結果無異議/ }).click();
  await expect(page).toHaveURL(/\/capture\/payment\?case_id=CASE-1044/);
  await expect(page.getByRole('heading', { name: '選擇付款方式' })).toBeVisible();
  await expect(page.getByText('本次最終應付金額')).toBeVisible();
  await expect(page.getByText('NT$5,500')).toBeVisible();
  await expect(page.getByRole('radio', { name: /銀行轉帳/ })).toBeChecked();
  await page.getByRole('link', { name: '返回 AI 判讀結果' }).click();
  await page.getByRole('link', { name: /申請人工覆核/ }).click();
  await expect(page).toHaveURL(/\/capture\/review-request\?case_id=CASE-1044/);
  await expect(page.getByRole('heading', { name: '你對哪些判讀結果有疑義？' })).toBeVisible();
  await page.getByRole('link', { name: /確認送出人工覆核申請/ }).click();
  await expect(page.getByRole('alert')).toHaveText('請至少勾選一項有疑義的 AI 判讀結果');
  await page.getByRole('checkbox', { name: /右後保桿出現疑似新增刮痕/ }).click();
  await page.getByLabel('補充說明').fill('這道痕跡在取車前就已存在，請協助比對。');
  await page.getByRole('link', { name: /確認送出人工覆核申請/ }).click();
  await expect(page).toHaveURL(/\/capture\/review-progress\?case_id=CASE-1044/);
  await expect(page.getByRole('heading', { name: '人工審核中', level: 1 })).toBeVisible();
  await expect(page.getByText('已完成 3 \/ 5 階段')).toBeVisible();
});

test('暫時分析頁選擇成功後完成還車檢查', async ({ page }) => {
  await page.goto('/capture/analysis-demo');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /成功/ }).click();
  await expect(page).toHaveURL(/\/capture\/result\?case_id=CASE-1043/);
  await expect(page.getByRole('heading', { name: '還車檢查已完成' })).toBeVisible();
});

test('暫時分析頁選擇失敗後進入分析結果', async ({ page }) => {
  await page.goto('/capture/analysis-demo');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /失敗/ }).click();
  await expect(page).toHaveURL(/\/capture\/result\?case_id=CASE-1044/);
  await expect(page.getByRole('heading', { name: 'AI 偵測到 2 處疑似問題' })).toBeVisible();
});

test('營運端可篩選並建立維修任務', async ({ page }) => {
  await page.goto('/review');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: '高風險', exact: true }).click();
  await expect(page.getByText('車輛 7A21').first()).toBeVisible();
  await page.getByRole('button', { name: /建立維修任務/ }).click();
  await expect(page.getByRole('status')).toContainText('待維修');
});

test('WebMCP 工具可更新同一份案件狀態並拒絕非法輸入', async ({ page }) => {
  await page.addInitScript(() => {
    type RegisteredTool = { name: string; execute: (input: unknown) => unknown };
    const target = window as unknown as { __caseTool?: RegisteredTool };
    Object.defineProperty(document, 'modelContext', {
      value: {
        registerTool(tool: RegisteredTool) {
          target.__caseTool = tool;
        },
      },
      configurable: true,
    });
  });
  await page.goto('/review');
  await page.waitForLoadState('networkidle');
  await page.waitForFunction(() => Boolean((window as unknown as { __caseTool?: unknown }).__caseTool));

  const valid = await page.evaluate(async () => {
    const tool = (window as unknown as { __caseTool: { name: string; execute: (input: unknown) => unknown } }).__caseTool;
    const result = await tool.execute({ caseId: 'CASE-1044', status: '已結案' });
    return { name: tool.name, result };
  });
  expect(valid.name).toBe('update_case_status');
  await expect(page.getByRole('status')).toContainText('已結案');

  const rejected = await page.evaluate(async () => {
    const tool = (window as unknown as { __caseTool: { execute: (input: unknown) => unknown } }).__caseTool;
    try {
      await tool.execute({ caseId: 'CASE-1044', status: '非法狀態' });
      return false;
    } catch {
      return true;
    }
  });
  expect(rejected).toBe(true);
});
