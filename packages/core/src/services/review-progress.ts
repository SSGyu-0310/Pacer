import type { ReviewQueueItem, ReviewReviewerCounts } from "../ports";

type ReviewProgressItem = Pick<ReviewQueueItem, "latestVerdict" | "latestReviewer">;

export function countReviewers(items: ReviewProgressItem[]): ReviewReviewerCounts {
  const counts: ReviewReviewerCounts = {
    shin: 0,
    kwon: 0,
    other: 0,
    pending: 0,
    total: items.length,
    decided: 0,
  };
  for (const item of items) {
    if (!item.latestVerdict) {
      counts.pending += 1;
      continue;
    }
    counts.decided += 1;
    if (item.latestReviewer === "shin") counts.shin += 1;
    else if (item.latestReviewer === "kwon") counts.kwon += 1;
    else counts.other += 1;
  }
  return counts;
}
