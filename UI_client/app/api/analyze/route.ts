import { analyses, nextStatus, type ScenarioKey } from '@/lib/prototype';

export async function POST(request: Request) {
  const formData = await request.formData();
  const rawScenario = formData.get('scenario');
  const scenario: ScenarioKey =
    typeof rawScenario === 'string' && rawScenario in analyses
      ? (rawScenario as ScenarioKey)
      : 'normal';
  const result = analyses[scenario];

  await new Promise((resolve) => setTimeout(resolve, 700));

  return Response.json({
    ...result,
    status: nextStatus(result.recommended_action),
    analyzed_at: new Date().toISOString(),
    source: 'mock-api',
  });
}
