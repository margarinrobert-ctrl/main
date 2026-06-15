import type { ScoredContract } from "../flow/heuristic";

export interface FlowSnapshot {
  takenAt: string;
  rows: ScoredContract[];
}

export interface SnapshotStore {
  save(snapshot: FlowSnapshot): Promise<void>;
  recent(limit: number): Promise<FlowSnapshot[]>;
}

class InMemorySnapshotStore implements SnapshotStore {
  private snapshots: FlowSnapshot[] = [];

  async save(snapshot: FlowSnapshot): Promise<void> {
    this.snapshots.unshift(snapshot);
    this.snapshots = this.snapshots.slice(0, 500);
  }

  async recent(limit: number): Promise<FlowSnapshot[]> {
    return this.snapshots.slice(0, limit);
  }
}

/**
 * Drop in a Prisma/Postgres-backed implementation later — same interface.
 * Deferred for the MVP: meaningful flow-over-time needs the PAID live screener
 * plus background polling, so there's nothing to persist on the free tier yet.
 */
export const snapshotStore: SnapshotStore = new InMemorySnapshotStore();
