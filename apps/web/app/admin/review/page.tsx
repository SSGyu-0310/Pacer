import { requireAdminPage } from "@/lib/admin-auth";
import { AdminReviewApp } from "@/components/review/AdminReviewApp";

export default async function AdminReviewPage() {
  await requireAdminPage();
  return <AdminReviewApp />;
}
