import { describe, expect, it } from 'vitest';
import { analyses, nextStatus } from '@/lib/prototype';

describe('四種黃金情境', () => {
  it('模糊或角度錯誤時要求補拍', () => {
    expect(analyses.blur.capture_quality.passed).toBe(false);
    expect(nextStatus(analyses.blur.recommended_action)).toBe('AI完成');
  });

  it('正常車況自動放行並結案', () => {
    expect(analyses.normal.risk_level).toBe('low');
    expect(nextStatus(analyses.normal.recommended_action)).toBe('已結案');
  });

  it('疑似新車損送人工覆核', () => {
    expect(analyses.damage.vehicle_change.detected).toBe(true);
    expect(nextStatus(analyses.damage.recommended_action)).toBe('待人工覆核');
  });

  it('髒污案件建立清潔任務', () => {
    expect(analyses.dirty.cleanliness.level).toBe('dirty');
    expect(nextStatus(analyses.dirty.recommended_action)).toBe('待清潔');
  });
});
