export type ScenarioKey = 'blur' | 'normal' | 'damage' | 'dirty';
export type RiskLevel = 'low' | 'medium' | 'high';
export type RecommendedAction = 'pass' | 'reshoot' | 'human_review' | 'cleaning' | 'maintenance';
export type CaseStatus = '待分析' | 'AI完成' | '待人工覆核' | '待清潔' | '待維修' | '已結案';
export type ReviewStatus = 'not_required' | 'pending_human_review';

export type DamageFinding = {
  id: string;
  shot_type: string;
  shot_label: string;
  summary: string;
  confidence: number;
  severity: 'low' | 'medium' | 'high';
  photo_id: string;
  estimated_cost: {
    currency: 'TWD';
    min: number;
    max: number;
  };
};

export type CompensationEstimate = {
  currency: 'TWD';
  min: number;
  max: number;
  final_amount: number;
  provisional: true;
  category: 'damage' | 'cleaning' | 'maintenance';
};

export type AnalysisResult = {
  case_id: string;
  capture_quality: { passed: boolean; issues: string[] };
  vehicle_change: { detected: boolean; findings: string[] };
  cleanliness: { level: 'clean' | 'normal' | 'dirty'; findings: string[] };
  risk_level: RiskLevel;
  confidence: number;
  recommended_action: RecommendedAction;
  damage_findings: DamageFinding[];
  compensation_estimate: CompensationEstimate | null;
  review_status: ReviewStatus;
};

export type ReviewCase = AnalysisResult & {
  stage: 'pickup' | 'return';
  vehicle: string;
  location: string;
  submittedAt: string;
  status: CaseStatus;
  summary: string;
};

export const scenarioLabels: Record<ScenarioKey, string> = {
  blur: '照片模糊',
  normal: '正常車況',
  damage: '疑似新車損',
  dirty: '車內髒污',
};

export const analyses: Record<ScenarioKey, AnalysisResult> = {
  blur: {
    case_id: 'CASE-1042',
    capture_quality: { passed: false, issues: ['blur', 'wrong_angle'] },
    vehicle_change: { detected: false, findings: [] },
    cleanliness: { level: 'normal', findings: [] },
    risk_level: 'medium',
    confidence: 0.91,
    recommended_action: 'reshoot',
    damage_findings: [],
    compensation_estimate: null,
    review_status: 'not_required',
  },
  normal: {
    case_id: 'CASE-1043',
    capture_quality: { passed: true, issues: [] },
    vehicle_change: { detected: false, findings: [] },
    cleanliness: { level: 'clean', findings: ['座椅與腳踏區域未見明顯髒污'] },
    risk_level: 'low',
    confidence: 0.94,
    recommended_action: 'pass',
    damage_findings: [],
    compensation_estimate: null,
    review_status: 'not_required',
  },
  damage: {
    case_id: 'CASE-1044',
    capture_quality: { passed: true, issues: [] },
    vehicle_change: { detected: true, findings: ['右後保桿出現新增刮痕候選區域'] },
    cleanliness: { level: 'normal', findings: [] },
    risk_level: 'high',
    confidence: 0.78,
    recommended_action: 'human_review',
    damage_findings: [
      {
        id: 'FINDING-1044-01',
        shot_type: 'rear_right_45',
        shot_label: '車尾右後方 45°',
        summary: '右後保桿出現疑似新增刮痕',
        confidence: 0.78,
        severity: 'medium',
        photo_id: 'IMG-1044-04',
        estimated_cost: { currency: 'TWD', min: 2000, max: 4000 },
      },
      {
        id: 'FINDING-1044-02',
        shot_type: 'front_right_45',
        shot_label: '車頭右前方 45°',
        summary: '右前車門下緣出現疑似新增凹痕',
        confidence: 0.74,
        severity: 'medium',
        photo_id: 'IMG-1044-05',
        estimated_cost: { currency: 'TWD', min: 1500, max: 3000 },
      },
    ],
    compensation_estimate: {
      currency: 'TWD',
      min: 3500,
      max: 7000,
      final_amount: 5500,
      provisional: true,
      category: 'damage',
    },
    review_status: 'pending_human_review',
  },
  dirty: {
    case_id: 'CASE-1045',
    capture_quality: { passed: true, issues: [] },
    vehicle_change: { detected: false, findings: [] },
    cleanliness: { level: 'dirty', findings: ['後座有飲料杯與明顯垃圾'] },
    risk_level: 'high',
    confidence: 0.88,
    recommended_action: 'cleaning',
    damage_findings: [
      {
        id: 'FINDING-1045-01',
        shot_type: 'rear_cabin',
        shot_label: '後座與腳踏區',
        summary: '後座發現飲料杯與明顯垃圾，可能需要額外清潔',
        confidence: 0.88,
        severity: 'medium',
        photo_id: 'IMG-1045-07',
        estimated_cost: { currency: 'TWD', min: 500, max: 1200 },
      },
    ],
    compensation_estimate: {
      currency: 'TWD',
      min: 500,
      max: 1200,
      final_amount: 800,
      provisional: true,
      category: 'cleaning',
    },
    review_status: 'pending_human_review',
  },
};

export const initialCases: ReviewCase[] = [
  {
    ...analyses.damage,
    stage: 'return',
    vehicle: '車輛 7A21',
    location: '台北市信義區',
    submittedAt: '今天 10:18',
    status: '待人工覆核',
    summary: '右後保桿疑似新增刮痕',
  },
  {
    ...analyses.dirty,
    stage: 'return',
    vehicle: '車輛 3C08',
    location: '新北市板橋區',
    submittedAt: '今天 10:11',
    status: '待清潔',
    summary: '後座垃圾，建議立即清潔',
  },
  {
    ...analyses.blur,
    stage: 'pickup',
    vehicle: '車輛 5B16',
    location: '台北市中山區',
    submittedAt: '今天 09:56',
    status: 'AI完成',
    summary: '照片模糊且角度偏移，已要求補拍',
  },
  {
    ...analyses.normal,
    stage: 'return',
    vehicle: '車輛 8D33',
    location: '台北市大安區',
    submittedAt: '今天 09:42',
    status: '已結案',
    summary: '未發現新增異常',
  },
];

export function nextStatus(action: RecommendedAction): CaseStatus {
  const map: Record<RecommendedAction, CaseStatus> = {
    pass: '已結案',
    reshoot: 'AI完成',
    human_review: '待人工覆核',
    cleaning: '待清潔',
    maintenance: '待維修',
  };
  return map[action];
}
