import { PrismaClient } from "@prisma/client";

/** 단일 PrismaClient 인스턴스 (개발 중 HMR 다중 생성 방지). */
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const prisma: PrismaClient = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
