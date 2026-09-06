import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Navbar } from "@/components/site/navbar";
import { ScoreBanner } from "@/components/result/score-banner";
import { ShareActions } from "@/components/result/share-actions";
import { SeverityChart } from "@/components/result/severity-chart";
import { MetricsStrip } from "@/components/result/metrics-strip";
import { RoastPanel } from "@/components/result/roast-panel";
import { HighlightsList } from "@/components/result/highlights-list";
import { FixesList } from "@/components/result/fixes-list";
import { ExpiredView } from "@/components/result/expired-view";
import { ApiError, getRoastAnalysis, publicRoastCardUrl } from "@/lib/api";

type PageParams = { params: Promise<{ slug: string }> };

// Server-rendered (not a client component like the rest of this build) --
// this page's entire point is being pasted into Slack/Twitter/etc., and
// those unfurl previews are generated from server-rendered <meta> tags, not
// by executing client JS. generateMetadata below is what actually makes the
// roast card image show up in a shared link's preview.
export async function generateMetadata({ params }: PageParams): Promise<Metadata> {
  const { slug } = await params;
  try {
    const data = await getRoastAnalysis(slug);
    const imageUrl = publicRoastCardUrl(slug);
    const title = `${data.composite_score}/100 -- Resume Roast Arena`;
    return {
      title,
      description: data.verdict,
      openGraph: {
        title: `${data.stamp} -- ${data.composite_score}/100`,
        description: data.verdict,
        images: [{ url: imageUrl, width: 1080, height: 1350 }],
      },
      twitter: {
        card: "summary_large_image",
        title: `${data.stamp} -- ${data.composite_score}/100`,
        description: data.verdict,
        images: [imageUrl],
      },
    };
  } catch {
    return { title: "Roast Result -- Resume Roast Arena" };
  }
}

export default async function ResultPage({ params }: PageParams) {
  const { slug } = await params;

  let data;
  try {
    data = await getRoastAnalysis(slug);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    if (err instanceof ApiError && err.status === 410) return <ExpiredView />;
    throw err;
  }

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden bg-brand-blue font-mono selection:bg-brand-lime selection:text-brand-blue">
      <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(to_right,#ffffff15_1px,transparent_1px),linear-gradient(to_bottom,#ffffff15_1px,transparent_1px)] bg-[size:4rem_4rem]" />

      <Navbar />

      <main className="relative z-10 mx-auto flex w-full max-w-[1440px] flex-1 flex-col items-center px-4 pb-16 pt-4 md:px-10">
        <div className="flex w-full flex-col items-center gap-8 md:flex-row md:items-center md:justify-center md:gap-16">
          {/* eslint-disable-next-line @next/next/no-img-element -- dynamically rendered per-slug from a separate backend origin, not a static/Next-optimizable asset */}
          <img
            src={publicRoastCardUrl(slug)}
            alt="Your roast card"
            width={420}
            height={525}
            className="w-full max-w-[300px] flex-shrink-0 rounded-2xl shadow-2xl md:max-w-[360px]"
          />
          <div className="flex flex-col items-center gap-6">
            <ScoreBanner
              score={data.composite_score}
              stamp={data.stamp}
              rank={data.rank}
              totalRanked={data.total_ranked}
            />
            <ShareActions slug={slug} />
          </div>
        </div>
      </main>

      <section className="relative z-20 mt-auto w-full rounded-t-[2.5rem] bg-white px-6 py-12 text-black shadow-[0_-20px_50px_rgba(0,0,0,0.2)] md:rounded-t-[3.5rem] md:px-10 md:py-16">
        <div className="mx-auto flex max-w-4xl flex-col gap-10">
          <SeverityChart summary={data.summary} />
          <MetricsStrip metrics={data.metrics} />
          <RoastPanel verdict={data.verdict} roast={data.roast} />
          <HighlightsList highlights={data.highlights} />
          <FixesList fixes={data.fixes} />

          <div className="flex flex-col items-center gap-3 border-t border-black/10 pt-8 text-center">
            <p className="font-mono text-xs text-smoke">Think you can do better?</p>
            <Link
              href="/roast"
              className="flex items-center gap-2 rounded-full bg-brand-blue px-8 py-4 font-display text-sm uppercase tracking-wide text-white shadow-[4px_4px_0_#000] transition-all hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0_#000] md:text-base"
            >
              Roast your own resume
              <ArrowRight size={18} strokeWidth={2.5} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
