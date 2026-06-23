import { describe, expect, it } from "vitest";
import { countReviewers } from "../review-progress";

describe("countReviewers", () => {
  it("신/권/기타/pending 진행률을 latest decision 기준으로 집계한다", () => {
    expect(
      countReviewers([
        { latestVerdict: "edit", latestReviewer: "shin" },
        { latestVerdict: "confirm", latestReviewer: "kwon" },
        { latestVerdict: "flag", latestReviewer: "solo" },
        { latestVerdict: "skip", latestReviewer: "agent:core-rule-fill" },
        { latestVerdict: "reject", latestReviewer: null },
        { latestVerdict: null, latestReviewer: "shin" },
      ]),
    ).toEqual({
      shin: 1,
      kwon: 1,
      other: 3,
      pending: 1,
      total: 6,
      decided: 5,
    });
  });
});
