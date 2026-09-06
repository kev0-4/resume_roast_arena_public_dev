import { LogOut } from "lucide-react";
import { Avatar } from "@/components/leaderboard/avatar";

function memberSince(isoDate: string | null): string {
  if (!isoDate) return "";
  return new Date(isoDate).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

export function ProfileHeader({
  displayName,
  createdAt,
  onSignOut,
}: {
  displayName: string;
  createdAt: string | null;
  onSignOut: () => void;
}) {
  return (
    <div className="flex items-center gap-4 rounded-2xl border-[3px] border-black bg-white px-5 py-4 shadow-[5px_5px_0_#000] md:px-7">
      <Avatar name={displayName} size={44} />
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-display text-lg text-black md:text-xl">{displayName}</h1>
        {createdAt && <p className="mt-0.5 font-mono text-xs font-semibold text-black/45">Member since {memberSince(createdAt)}</p>}
      </div>
      <button
        onClick={onSignOut}
        className="flex flex-shrink-0 items-center gap-1.5 rounded-full border-2 border-black bg-white px-4 py-2 font-mono text-xs font-bold text-black transition-colors hover:bg-black hover:text-white"
      >
        <LogOut size={13} />
        Sign out
      </button>
    </div>
  );
}
