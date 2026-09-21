import type { AnalysisResult, CaseStatus } from '@/lib/prototype';

export type CaptureStep = {
  shotType: string;
  title: string;
  description: string;
  frameLabel: string;
  tips: [string, string, string];
};

export type StoredAnalysisResult = AnalysisResult & {
  status: CaseStatus;
  analyzed_at: string;
  source: string;
};

export type CaptureDraft = {
  photoCount: number;
  normalPhotoCount?: number;
  damagePhotoCount?: number;
  thumbnails: Record<string, string>;
};

export const captureSteps: CaptureStep[] = [
  {
    shotType: 'vehicle_cards',
    title: '加油卡與停車卡',
    description: '將加油卡與停車卡並排放好，確認卡片正面、文字與卡號位置清楚可辨。',
    frameLabel: '兩張卡片需完整入鏡',
    tips: ['卡片並排', '文字清楚', '避免反光'],
  },
  {
    shotType: 'dashboard',
    title: '儀表板與里程',
    description: '坐在駕駛座拍攝完整儀表板，讓剩餘油量、警示燈與里程數字清楚可見。',
    frameLabel: '里程與油量需清楚',
    tips: ['儀表亮起', '數字清晰', '保持水平'],
  },
  {
    shotType: 'front_cabin',
    title: '車內座椅（前座）',
    description: '由前車門拍攝駕駛座、副駕座與中控區域，確認座椅及腳踏區沒有髒污或遺留物。',
    frameLabel: '前座與中控完整入鏡',
    tips: ['前座完整', '中控清楚', '移除物品'],
  },
  {
    shotType: 'rear_cabin',
    title: '車內座椅（後座）',
    description: '由後車門拍攝後座椅面、椅背與腳踏區，讓清潔狀況完整且清楚可辨。',
    frameLabel: '後座與腳踏區完整入鏡',
    tips: ['椅面完整', '腳踏清楚', '光線充足'],
  },
  {
    shotType: 'front_left_45',
    title: '車身左前方 45°',
    description: '退後約 2 至 3 公尺，將完整車頭、左側車身與車牌放入取景框。',
    frameLabel: '車頭與左側車身需完整',
    tips: ['左前 45°', '完整入鏡', '光線充足'],
  },
  {
    shotType: 'front_right_45',
    title: '車身右前方 45°',
    description: '站在車頭右前方，讓完整車頭、右側車身與車牌保持清楚。',
    frameLabel: '車頭與右側車身需完整',
    tips: ['右前 45°', '退後 2–3 公尺', '避免逆光'],
  },
  {
    shotType: 'rear_left_45',
    title: '車身左後方 45°',
    description: '將完整車尾、左側車身及後車牌放入畫面，避免裁切保桿。',
    frameLabel: '車尾與左側車身需完整',
    tips: ['左後 45°', '車尾完整', '照片清晰'],
  },
  {
    shotType: 'rear_right_45',
    title: '車身右後方 45°',
    description: '站在車尾右後方，確認右側鈑件、後保桿與車牌都清楚可見。',
    frameLabel: '車尾與右側車身需完整',
    tips: ['右後 45°', '保桿完整', '避免陰影'],
  },
];

export const damageCaptureSteps: CaptureStep[] = Array.from({ length: 4 }, (_, index) => ({
  shotType: `damage_${index + 1}`,
  title: `損壞照片 ${index + 1}`,
  description: '請靠近損壞部位拍攝，並保留周圍車身作為位置參考。沒有其他車損時，可直接完成並進入分析。',
  frameLabel: '損壞處與周圍鈑件需清楚',
  tips: ['近距離清楚', '保留位置線索', '避免反光'],
}));

const resultPrefix = 'capture-analysis:';
const latestResultKey = 'capture-analysis:latest';
const thumbnailsPrefix = 'capture-thumbnails:';
const captureDraftKey = 'capture-analysis:draft';

export function saveCaptureResult(result: StoredAnalysisResult) {
  sessionStorage.setItem(`${resultPrefix}${result.case_id}`, JSON.stringify(result));
  sessionStorage.setItem(latestResultKey, result.case_id);
}

export function readCaptureResult(caseId?: string | null): StoredAnalysisResult | null {
  const resolvedId = caseId || sessionStorage.getItem(latestResultKey);
  if (!resolvedId) return null;

  try {
    const parsed = JSON.parse(sessionStorage.getItem(`${resultPrefix}${resolvedId}`) || 'null');
    return parsed && typeof parsed.case_id === 'string' ? parsed as StoredAnalysisResult : null;
  } catch {
    return null;
  }
}

export function saveCaptureThumbnails(caseId: string, thumbnails: Record<string, string>) {
  try {
    sessionStorage.setItem(`${thumbnailsPrefix}${caseId}`, JSON.stringify(thumbnails));
  } catch {
    // The result remains usable if browser storage is full; the UI will use a placeholder.
  }
}

export function readCaptureThumbnails(caseId: string): Record<string, string> {
  try {
    return JSON.parse(sessionStorage.getItem(`${thumbnailsPrefix}${caseId}`) || '{}');
  } catch {
    return {};
  }
}

export function saveCaptureDraft(draft: CaptureDraft) {
  try {
    sessionStorage.setItem(captureDraftKey, JSON.stringify(draft));
  } catch {
    sessionStorage.setItem(captureDraftKey, JSON.stringify({ photoCount: draft.photoCount, thumbnails: {} }));
  }
}

export function readCaptureDraft(): CaptureDraft | null {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(captureDraftKey) || 'null');
    return parsed && typeof parsed.photoCount === 'number' ? parsed as CaptureDraft : null;
  } catch {
    return null;
  }
}

export function clearCaptureDraft() {
  sessionStorage.removeItem(captureDraftKey);
}
