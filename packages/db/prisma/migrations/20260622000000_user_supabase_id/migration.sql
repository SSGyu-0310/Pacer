-- Add Supabase Auth stable identifier for Kakao/Google social login.
-- Created for review only; do not apply to the shared production Supabase from agents.
ALTER TABLE "users" ADD COLUMN "supabaseId" TEXT;

CREATE UNIQUE INDEX "users_supabaseId_key" ON "users"("supabaseId");
