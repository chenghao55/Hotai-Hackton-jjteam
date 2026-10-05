import { expect, test } from '@playwright/test';

const moduleEOrigin = 'http://127.0.0.1:8000';

test('拍照規則進入七個步驟的正式還車相機流程', async ({ page }) => {
  await page.goto('/capture');
  await page.waitForLoadState('networkidle');
  await page.getByTestId('rules-scroll-area').evaluate((element) => {
    element.scrollTop = element.scrollHeight - element.clientHeight;
    element.dispatchEvent(new Event('scroll', { bubbles: true }));
  });
  await page.waitForTimeout(100);
  await page.getByRole('checkbox', { name: '我已經詳細閱讀拍照規則及流程' }).click();
  await page.getByRole('link', { name: /開始拍照/ }).click();

  await expect(page).toHaveURL(/\/capture\/camera$/);
  await page.getByRole('button', { name: /轎車/ }).click();
  await expect(page.getByText('基本照片 1／7')).toBeVisible();
  await expect(page.getByRole('heading', { name: '加油卡與停車卡' })).toBeVisible();
  await expect(page.getByText(/dashboard/i)).toHaveCount(0);
  await expect(page.getByRole('button', { name: '跳過此張' })).toHaveCount(0);
});

test('七張正式照片與額外車損會走 Module E，Case 只包含 damage evidence IDs', async ({ page }) => {
  const uploadedSlots: string[] = [];
  let casePayload: Record<string, unknown> | null = null;

  await page.route(`${moduleEOrigin}/photos`, async (route) => {
    const request = route.request();
    const body = request.postDataBuffer()?.toString('utf8') ?? '';
    const slot = [
      'fuel_parking_card',
      'interior_front',
      'interior_rear',
      'front_left',
      'front_right',
      'rear_left',
      'rear_right',
      'other_damage',
    ].find((value) => body.includes(value));
    expect(body).toContain('return');
    expect(slot).toBeTruthy();
    uploadedSlots.push(slot!);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify({
        accepted: true,
        photo_id: `photo-${uploadedSlots.length}`,
        check: { level: 'PASS', code: 'PASS', message: '拍攝成功', action: 'accept' },
      }),
    });
  });

  await page.route(`${moduleEOrigin}/cases/from-photos`, async (route) => {
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Headers': 'content-type',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
        },
      });
      return;
    }
    casePayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      headers: { 'Access-Control-Allow-Origin': '*' },
      body: JSON.stringify({
        case_id: 'case-from-module-e',
        status: 'unassigned',
        priority_score: null,
        payment_amount: 0,
        detections: [],
      }),
    });
  });

  await page.goto('/capture/camera');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /轎車/ }).click();
  await expect(page.locator('input[type="file"]')).toBeAttached();

  const fileInput = page.locator('input[type="file"]');
  const nextHeadings = [
    '車內座椅（前座）',
    '車內座椅（後座）',
    '車身左前方 45°',
    '車身右前方 45°',
    '車身左後方 45°',
    '車身右後方 45°',
  ];
  for (let index = 0; index < 7; index += 1) {
    await fileInput.setInputFiles({ name: `photo-${index}.jpg`, mimeType: 'image/jpeg', buffer: Buffer.from(`photo-${index}`) });
    await page.getByRole('button', { name: /儲存並/ }).click();
    if (index < nextHeadings.length) {
      await expect(page.getByRole('heading', { name: nextHeadings[index] })).toBeVisible();
    }
  }

  await expect(page.getByRole('heading', { name: /是否有需要補拍的車損/ })).toBeVisible();
  await page.getByRole('button', { name: /新增損壞照片/ }).click();
  await fileInput.setInputFiles({ name: 'damage.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('damage') });
  await page.getByRole('button', { name: /完成並建立案件/ }).click();

  await expect(page).toHaveURL(/\/capture\/result\?case_id=case-from-module-e$/);
  await expect(page.getByText('case-from-module-e')).toBeVisible();
  expect(uploadedSlots).toEqual([
    'fuel_parking_card',
    'interior_front',
    'interior_rear',
    'front_left',
    'front_right',
    'rear_left',
    'rear_right',
    'other_damage',
  ]);
  expect(casePayload).toEqual({ photo_ids: ['photo-2', 'photo-3', 'photo-4', 'photo-5', 'photo-6', 'photo-7', 'photo-8'] });
  expect(casePayload).not.toHaveProperty('case_id');
});

test('營運端 prototype 仍可獨立運作', async ({ page }) => {
  await page.goto('/review');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: '高風險', exact: true }).click();
  await expect(page.getByText('車輛 7A21').first()).toBeVisible();
});

test('保留的付款與人工覆核 prototype 可直接操作', async ({ page }) => {
  await page.goto('/capture/payment?case_id=CASE-1044');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading', { name: '選擇付款方式' })).toBeVisible();
  await expect(page.getByText('NT$5,500')).toBeVisible();
  await expect(page.getByRole('radio', { name: /銀行轉帳/ })).toBeChecked();

  await page.goto('/capture/review-request?case_id=CASE-1044');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading', { name: '你對哪些判讀結果有疑義？' })).toBeVisible();
  await page.getByRole('link', { name: /確認送出人工覆核申請/ }).click();
  await expect(page.getByRole('alert')).toHaveText('請至少勾選一項有疑義的 AI 判讀結果');
  await page.getByRole('checkbox', { name: /右後保桿出現疑似新增刮痕/ }).click();
  await page.getByLabel('補充說明').fill('這道痕跡在取車前就已存在，請協助比對。');
  await page.getByRole('link', { name: /確認送出人工覆核申請/ }).click();
  await expect(page).toHaveURL(/\/capture\/review-progress\?case_id=CASE-1044/);
  await expect(page.getByRole('heading', { name: '人工審核中', level: 1 })).toBeVisible();
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
