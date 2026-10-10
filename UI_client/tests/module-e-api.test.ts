import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ModuleERequestError,
  createCaseFromPhotos,
  forceSavePhotoForDevelopment,
  isDevelopmentForceSaveEnabled,
  requestPhotoGuidance,
  uploadPhoto,
} from '@/lib/module-e-api';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('Module E API client', () => {
  beforeEach(() => vi.unstubAllGlobals());

  it('sends a live frame as multipart guidance input', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ accepted: true, check: { level: 'PASS', code: 'PASS', message: '可以拍攝', action: 'accept' } }));
    vi.stubGlobal('fetch', fetchMock);

    await requestPhotoGuidance(new Blob(['frame'], { type: 'image/jpeg' }), {
      photoType: 'return', captureSlot: 'interior_front', vehicleType: 'sedan',
      sessionId: 'session-1', frameId: 1, entrySide: 'left',
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:8000/photo-guidance');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('file')).toBeInstanceOf(File);
    expect((init.body as FormData).get('photo_type')).toBe('return');
    expect((init.body as FormData).get('capture_slot')).toBe('interior_front');
    expect((init.body as FormData).get('vehicle_type')).toBe('sedan');
    expect((init.body as FormData).get('session_id')).toBe('session-1');
    expect((init.body as FormData).get('frame_id')).toBe('1');
    expect((init.body as FormData).get('entry_side')).toBe('left');
  });

  it('uploads return photos with their canonical capture slot', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ accepted: true, photo_id: 'server-photo', check: { level: 'PASS', code: 'PASS', message: '已接受', action: 'accept' } }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await uploadPhoto(new Blob(['photo'], { type: 'image/jpeg' }), {
      photoType: 'return', captureSlot: 'front_left', vehicleType: 'suv',
      sessionId: 'session-1', frameId: 2,
    });

    const [, init] = fetchMock.mock.calls[0];
    const form = init.body as FormData;
    expect(form.get('photo_type')).toBe('return');
    expect(form.get('capture_slot')).toBe('front_left');
    expect(form.get('vehicle_type')).toBe('suv');
    expect(form.get('session_id')).toBe('session-1');
    expect(form.get('frame_id')).toBe('2');
    expect(form.has('entry_side')).toBe(false);
    expect(response.photo_id).toBe('server-photo');
  });

  it('returns accepted=false as a valid upload result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ accepted: false, photo_id: null, check: { level: 'L2', code: 'BLUR', message: '請重新拍攝', action: 'reshoot' } })));

    await expect(uploadPhoto(new Blob(['blur']), {
      photoType: 'return', captureSlot: 'rear_right', vehicleType: 'sedan',
      sessionId: 'session-1', frameId: 3,
    })).resolves.toMatchObject({ accepted: false, photo_id: null });
  });

  it('uses the isolated development force-save endpoint and receives a backend photo ID', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ photo_id: 'stored-by-backend' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(forceSavePhotoForDevelopment(new Blob(['rejected-final']), {
      photoType: 'return', captureSlot: 'front_left', vehicleType: 'sedan',
      sessionId: 'session-1', frameId: 4,
    })).resolves.toEqual({ photo_id: 'stored-by-backend' });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:8000/dev/photos/force-save');
    expect(init.body).toBeInstanceOf(FormData);
  });

  it('only enables the UI control in development mode', () => {
    expect(isDevelopmentForceSaveEnabled('development')).toBe(true);
    expect(isDevelopmentForceSaveEnabled('production')).toBe(false);
    expect(isDevelopmentForceSaveEnabled('test')).toBe(false);
  });

  it('creates a Case using only photo_ids and no client case_id', async () => {
    const result = { case_id: 'server-case', detections: [], priority_score: null, status: 'unassigned', payment_amount: 0 };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(result, 201));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createCaseFromPhotos(['return-1', 'return-2'])).resolves.toEqual(result);

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init.body))).toEqual({ photo_ids: ['return-1', 'return-2'] });
    expect(JSON.parse(String(init.body))).not.toHaveProperty('case_id');
  });

  it('distinguishes HTTP errors from network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(jsonResponse({ detail: 'invalid photos' }, 422)).mockRejectedValueOnce(new Error('offline')));

    await expect(createCaseFromPhotos(['photo-1'])).rejects.toMatchObject<Partial<ModuleERequestError>>({ kind: 'http', status: 422, message: 'invalid photos' });
    await expect(createCaseFromPhotos(['photo-1'])).rejects.toMatchObject<Partial<ModuleERequestError>>({ kind: 'network', status: null, message: 'offline' });
  });
});
