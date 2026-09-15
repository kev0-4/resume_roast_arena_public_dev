import { InterviewHistoryRow } from "./history-row";
import type { MyInterviewEntry } from "@/lib/interview-api";

// Same hard-shadow bordered card as dashboard/history-list.tsx's roast
// history -- kept as a separate component since it renders interview
// entries, not roast sessions, but intentionally matching that visual
// language for consistency across the app's two "list of past X" pages.
export function InterviewHistoryList({ interviews }: { interviews: MyInterviewEntry[] }) {
  return (
    <div className="w-full overflow-hidden rounded-2xl border-[3px] border-black bg-white shadow-[5px_5px_0_#000]">
      {interviews.map((entry) => (
        <InterviewHistoryRow key={entry.id} entry={entry} />
      ))}
    </div>
  );
}
