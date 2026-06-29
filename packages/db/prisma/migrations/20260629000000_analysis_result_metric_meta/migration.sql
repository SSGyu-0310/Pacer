ALTER TABLE "analysis_results"
  ADD COLUMN "metricMode" TEXT NOT NULL DEFAULT 'converted',
  ADD COLUMN "metricLabel" TEXT NOT NULL DEFAULT '환산점수',
  ADD COLUMN "cutLabel" TEXT NOT NULL DEFAULT '환산점수 컷';
