import type { CaptureSlot, CaseResponse } from '@/lib/module-e-api';

export type CaptureStep = {
  shotType: string;
  captureSlot: CaptureSlot;
  includeInCaseEvidence: boolean;
  title: string;
  description: string;
  frameLabel: string;
  tips: [string, string, string];
};

export type CapturedPhoto = {
  step: CaptureStep;
  photoId: string;
  thumbnail: string | null;
};

export const captureSteps: CaptureStep[] = [
  {
    shotType: 'vehicle_cards',
    captureSlot: 'fuel_parking_card',
    includeInCaseEvidence: false,
    title: '加油卡與停車卡',
    description: '將加油卡與停車卡並排放好，確認卡片正面、文字與卡號位置清楚可辨。',
    frameLabel: '兩張卡片需完整入鏡',
    tips: ['卡片並排', '文字清楚', '避免反光'],
  },
  {
    shotType: 'front_cabin',
    captureSlot: 'interior_front',
    includeInCaseEvidence: false,
    title: '車內座椅（前座）',
    description: '由前車門拍攝駕駛座、副駕座與中控區域，確認座椅及腳踏區沒有髒污或遺留物。',
    frameLabel: '前座與中控完整入鏡',
    tips: ['前座完整', '中控清楚', '移除物品'],
  },
  {
    shotType: 'rear_cabin',
    captureSlot: 'interior_rear',
    includeInCaseEvidence: false,
    title: '車內座椅（後座）',
    description: '由後車門拍攝後座椅面、椅背與腳踏區，讓清潔狀況完整且清楚可辨。',
    frameLabel: '後座與腳踏區完整入鏡',
    tips: ['椅面完整', '腳踏清楚', '光線充足'],
  },
  {
    shotType: 'front_left_45',
    captureSlot: 'front_left',
    includeInCaseEvidence: true,
    title: '車身左前方 45°',
    description: '退後約 2 至 3 公尺，將完整車頭、左側車身與車牌放入取景框。',
    frameLabel: '車頭與左側車身需完整',
    tips: ['左前 45°', '完整入鏡', '光線充足'],
  },
  {
    shotType: 'front_right_45',
    captureSlot: 'front_right',
    includeInCaseEvidence: true,
    title: '車身右前方 45°',
    description: '站在車頭右前方，讓完整車頭、右側車身與車牌保持清楚。',
    frameLabel: '車頭與右側車身需完整',
    tips: ['右前 45°', '退後 2–3 公尺', '避免逆光'],
  },
  {
    shotType: 'rear_left_45',
    captureSlot: 'rear_left',
    includeInCaseEvidence: true,
    title: '車身左後方 45°',
    description: '將完整車尾、左側車身及後車牌放入畫面，避免裁切保桿。',
    frameLabel: '車尾與左側車身需完整',
    tips: ['左後 45°', '車尾完整', '照片清晰'],
  },
  {
    shotType: 'rear_right_45',
    captureSlot: 'rear_right',
    includeInCaseEvidence: true,
    title: '車身右後方 45°',
    description: '站在車尾右後方，確認右側鈑件、後保桿與車牌都清楚可見。',
    frameLabel: '車尾與右側車身需完整',
    tips: ['右後 45°', '保桿完整', '避免陰影'],
  },
];

export const damageCaptureSteps: CaptureStep[] = Array.from({ length: 4 }, (_, index) => ({
  shotType: `damage_${index + 1}`,
  captureSlot: 'other_damage',
  includeInCaseEvidence: true,
  title: `損壞照片 ${index + 1}`,
  description: '請靠近損壞部位拍攝，並保留周圍車身作為位置參考。沒有其他車損時，可直接完成並進入分析。',
  frameLabel: '損壞處與周圍鈑件需清楚',
  tips: ['近距離清楚', '保留位置線索', '避免反光'],
}));

const resultPrefix = 'capture-case:';
const latestResultKey = 'capture-case:latest';
const thumbnailsPrefix = 'capture-thumbnails:';

export function saveCaptureResult(result: CaseResponse) {
  sessionStorage.setItem(`${resultPrefix}${result.case_id}`, JSON.stringify(result));
  sessionStorage.setItem(latestResultKey, result.case_id);
}

export function readCaptureResult(caseId?: string | null): CaseResponse | null {
  const resolvedId = caseId || sessionStorage.getItem(latestResultKey);
  if (!resolvedId) return null;

  try {
    const parsed = JSON.parse(sessionStorage.getItem(`${resultPrefix}${resolvedId}`) || 'null');
    return parsed && typeof parsed.case_id === 'string' ? parsed as CaseResponse : null;
  } catch {
    return null;
  }
}

export function saveCaptureThumbnails(caseId: string, thumbnails: Record<string, string>) {
  try {
    sessionStorage.setItem(`${thumbnailsPrefix}${caseId}`, JSON.stringify(thumbnails));
  } catch {
    // The Case remains usable if browser storage is full.
  }
}

export function readCaptureThumbnails(caseId: string): Record<string, string> {
  try {
    return JSON.parse(sessionStorage.getItem(`${thumbnailsPrefix}${caseId}`) || '{}');
  } catch {
    return {};
  }
}
