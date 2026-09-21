import Link from 'next/link';
import { Camera, ClipboardCheck, MoveRight, ShieldCheck } from 'lucide-react';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export default function Home() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-white/10 bg-[#101d1a] text-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-[#c9ff38] text-[#101d1a]">
              <ShieldCheck className="size-5" />
            </span>
            <div>
              <p className="font-semibold tracking-tight">車況管家</p>
              <p className="text-xs text-white/55">iRent AI Prototype</p>
            </div>
          </div>
          <span className="rounded-full border border-white/15 px-3 py-1 text-xs text-white/65">初賽展示版</span>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-5 py-10 sm:py-16">
        <div className="mb-8 max-w-2xl">
          <p className="mb-3 text-sm font-semibold text-[#276a5a]">選擇操作端</p>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-5xl">一條車況信任鏈，連接租車者與營運團隊</h1>
          <p className="mt-4 text-base leading-7 text-muted-foreground">從拍攝防呆、AI 判讀到人工覆核與派工，使用同一份案件資料完成閉環。</p>
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <article className="group rounded-[28px] border bg-card p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-xl sm:p-8">
            <div className="mb-10 flex items-start justify-between">
              <span className="grid size-14 place-items-center rounded-2xl bg-[#eaffaa] text-[#173e35]"><Camera className="size-7" /></span>
              <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">手機優先</span>
            </div>
            <h2 className="text-2xl font-semibold">租車者拍攝端</h2>
            <p className="mt-2 min-h-14 text-sm leading-6 text-muted-foreground">依序完成車外與車內拍攝，即時收到模糊、角度與距離補拍提示。</p>
            <Link href="/capture" className={cn(buttonVariants(), 'mt-7 w-full bg-[#173e35] text-white hover:bg-[#22594b]')}>開始車況檢查 <MoveRight className="size-4" /></Link>
          </article>

          <article className="group rounded-[28px] border bg-[#173e35] p-6 text-white shadow-sm transition hover:-translate-y-1 hover:shadow-xl sm:p-8">
            <div className="mb-10 flex items-start justify-between">
              <span className="grid size-14 place-items-center rounded-2xl bg-white/10 text-[#c9ff38]"><ClipboardCheck className="size-7" /></span>
              <span className="rounded-full border border-white/15 px-3 py-1 text-xs font-medium text-white/60">桌機優先</span>
            </div>
            <h2 className="text-2xl font-semibold">營運覆核端</h2>
            <p className="mt-2 min-h-14 text-sm leading-6 text-white/65">依風險查看案件，比較借還車差異，完成人工覆核、清潔或維修派工。</p>
            <Link href="/review" className={cn(buttonVariants(), 'mt-7 w-full bg-[#c9ff38] text-[#10251f] hover:bg-[#ddff7d]')}>進入案件中心 <MoveRight className="size-4" /></Link>
          </article>
        </div>
      </section>
    </main>
  );
}
