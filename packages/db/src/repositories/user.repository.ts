import type { User, UserRepository } from "@pacer/core";
import type { PrismaClient } from "@prisma/client";

export class PrismaUserRepository implements UserRepository {
  constructor(private readonly db: PrismaClient) {}

  async findBySupabaseId(supabaseId: string): Promise<User | null> {
    const row = await this.db.user.findUnique({ where: { supabaseId } });
    return row ? toDomain(row) : null;
  }

  async findById(id: string): Promise<User | null> {
    const row = await this.db.user.findUnique({ where: { id } });
    return row ? toDomain(row) : null;
  }

  async create(input: {
    supabaseId: string;
    email: string | null;
    phone: string | null;
    kakaoId: string | null;
  }): Promise<User> {
    const row = await this.db.user.create({
      data: {
        supabaseId: input.supabaseId,
        email: input.email,
        phone: input.phone,
        kakaoId: input.kakaoId,
      },
    });
    return toDomain(row);
  }
}

function toDomain(row: {
  id: string;
  supabaseId: string | null;
  email: string | null;
  phone: string | null;
  kakaoId: string | null;
  role: User["role"];
}): User {
  return {
    id: row.id,
    supabaseId: row.supabaseId,
    email: row.email,
    phone: row.phone,
    kakaoId: row.kakaoId,
    role: row.role,
  };
}
