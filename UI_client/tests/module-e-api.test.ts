import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ModuleERequestError,
  createCaseFromPhotos,
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
      vehicleType: 'suv', captureSlot: 'interior_rear', sessionId: 'capture-session',
      frameId: 4, entrySide: 'right',
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:8000/photo-guidance');
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('file')).toBeInstanceOf(File);
    expect((init.body as FormData).get('capture_slot')).toBe('interior_rear');
    expect((init.body as FormData).get('entry_side')).toBe('right');
    expect((init.body as FormData).get('frame_id')).toBe('4');
  });

  it('uploads return photos with their canonical capture slot', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ accepted: true, photo_id: 'server-photo', check: { level: 'PASS', code: 'PASS', message: '已接受', action: 'accept' } }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await uploadPhoto(new Blob(['photo'], { type: 'image/jpeg' }), 'return', 'front_left');

    const [, init] = fetchMock.mock.calls[0];
    const form = init.body as FormData;
    expect(form.get('photo_type')).toBe('return');
    expect(form.get('capture_slot')).toBe('front_left');
    expect(response.photo_id).toBe('server-photo');
  });

  it('returns accepted=false as a valid upload result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ accepted: false, photo_id: null, check: { level: 'L2', code: 'BLUR', message: '請重新拍攝', action: 'reshoot' } })));

    await expect(uploadPhoto(new Blob(['blur']), 'return', 'rear_right')).resolves.toMatchObject({ accepted: false, photo_id: null });
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
