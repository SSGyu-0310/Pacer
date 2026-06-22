import type { SavedUnit, SavedUnitInput } from "../domain/entities";
import type { SavedUnitRepository } from "../ports";

/** 관심 모집단위 저장(P0 내부 데모용 최소 기능). */
export class SavedUnitService {
  constructor(private readonly savedUnits: SavedUnitRepository) {}

  save(input: SavedUnitInput): Promise<SavedUnit> {
    return this.savedUnits.save(input);
  }

  list(cycleId: string): Promise<SavedUnit[]> {
    return this.savedUnits.list(cycleId);
  }
}
