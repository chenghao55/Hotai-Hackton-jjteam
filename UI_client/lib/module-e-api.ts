export type CaptureSlot =
  | 'front_left'
  | 'front_right'
  | 'rear_left'
  | 'rear_right'
  | 'rear'
  | 'interior_front'
  | 'interior_rear'
  | 'fuel_parking_card'
  | 'other_damage';

export type GuidanceLevel = 'L1' | 'L2' | 'L3' | 'L4' | 'L5' | 'L6' | 'PASS';
export type GuidanceCode =
  | 'TOO_DARK'
  | 'BACKLIGHT'
  | 'OVEREXPOSED'
  | 'BLUR'
  | 'TOO_FAR'
  | 'TOO_CLOSE'
  | 'OFF_CENTER'
  | 'ANGLE_TOO_HIGH'
  | 'ANGLE_TOO_LOW'
  | 'TOO_FRONT'
  | 'TOO_SIDE'
  | 'INTERIOR_NOT_ALIGNED'
  | 'LOW_DETAIL' | 'SUBJECT_NOT_DETECTED' | 'MULTIPLE_SUBJECTS'
  | 'SUBJECT_NEAR_EDGE' | 'SUBJECT_TOO_SMALL' | 'SUBJECT_TOO_LARGE'
  | 'POSSIBLE_WRONG_SLOT' | 'TEMPLATE_NOT_CALIBRATED'
  | 'FRONT_SEAT_EVIDENCE_UNAVAILABLE' | 'UNSUPPORTED_SLOT'
  | 'MISSING_REQUIRED_FEATURE' | 'GEOMETRY_MISMATCH' | 'AMBIGUOUS_TEMPLATES'
  | 'PASS';
export type GuidanceAction = 'guide' | 'reshoot' | 'accept';

export type PhotoCheck = {
  level: GuidanceLevel;
  code: GuidanceCode;
  message: string;
  action: GuidanceAction;
};

export type PhotoGuidanceResponse = {
  accepted: boolean;
  check: PhotoCheck;
};

export type CaptureContext = {
  vehicleType: 'sedan' | 'suv';
  captureSlot: CaptureSlot;
  sessionId: string;
  frameId: number;
  entrySide?: 'left' | 'right';
};

export type PhotoUploadResponse = PhotoGuidanceResponse & {
  photo_id: string | null;
};

export type DetectionResponse = {
  detection_id: string;
  borrow_photo_id: string | null;
  return_photo_id: string;
  source_photo_id: string | null;
  category: 'scratch' | 'collision_damage' | 'cleanliness';
  severity: 'minor' | 'moderate' | 'severe';
  confidence: number;
  review_state: 'needs_review' | 'auto_accepted' | 'confirmed' | 'rejected' | 'corrected';
  reviewed_category: 'scratch' | 'collision_damage' | 'cleanliness' | null;
  reviewed_severity: 'minor' | 'moderate' | 'severe' | null;
  review_note: string | null;
};

export type CaseResponse = {
  case_id: string;
  detections: DetectionResponse[];
  priority_score: number | null;
  status: 'unassigned' | 'dispatched' | 'processing' | 'pending_payment' | 'completed';
  payment_amount: number;
};

export class ModuleERequestError extends Error {
  readonly kind: 'network' | 'http';
  readonly status: number | null;

  constructor(message: string, kind: 'network' | 'http', status: number | null = null) {
    super(message);
    this.name = 'ModuleERequestError';
    this.kind = kind;
    this.status = status;
  }
}

const configuredBaseUrl = process.env.NEXT_PUBLIC_MODULE_E_BASE_URL?.trim();
export const MODULE_E_BASE_URL = (configuredBaseUrl || 'http://127.0.0.1:8000').replace(/\/$/, '');

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${MODULE_E_BASE_URL}${path}`, init);
  } catch (error) {
    throw new ModuleERequestError(
      error instanceof Error ? error.message : '無法連線至後端服務',
      'network',
    );
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === 'string' && body.detail.trim()) detail = body.detail;
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new ModuleERequestError(detail, 'http', response.status);
  }

  return response.json() as Promise<T>;
}

function imageForm(image: Blob): FormData {
  const form = new FormData();
  form.append('file', image, 'capture.jpg');
  return form;
}

function appendContext(form: FormData, context: CaptureContext) {
  form.append('vehicle_type', context.vehicleType);
  form.append('session_id', context.sessionId);
  form.append('frame_id', String(context.frameId));
  if (context.entrySide) form.append('entry_side', context.entrySide);
}

export function requestPhotoGuidance(image: Blob, context?: CaptureContext): Promise<PhotoGuidanceResponse> {
  const form = imageForm(image);
  if (context) {
    form.append('photo_type', 'return');
    form.append('capture_slot', context.captureSlot);
    appendContext(form, context);
  }
  return requestJson('/photo-guidance', { method: 'POST', body: form });
}

export function uploadPhoto(
  image: Blob,
  photoType: 'return',
  captureSlot: CaptureSlot,
  context?: CaptureContext,
): Promise<PhotoUploadResponse> {
  const form = imageForm(image);
  form.append('photo_type', photoType);
  form.append('capture_slot', captureSlot);
  if (context) appendContext(form, context);
  return requestJson('/photos', { method: 'POST', body: form });
}

export function createCaseFromPhotos(photoIds: string[]): Promise<CaseResponse> {
  return requestJson('/cases/from-photos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ photo_ids: photoIds }),
  });
}
