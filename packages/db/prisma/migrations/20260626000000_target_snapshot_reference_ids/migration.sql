ALTER TABLE "target_snapshots"
  ADD COLUMN "targetUniversityIds" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ADD COLUMN "targetUnitIds" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
