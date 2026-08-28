export interface CommunitySummary {
  id: string
  waId: string
  name: string
  pictureUrl: string | null
  memberCount: number
  groupCount: number
  adminCount: number
  pendingRequestCount: number
  lastSyncedAt: string
}

export interface CommunityDetail extends CommunitySummary {
  description: string | null
  announcementGroupWaId: string
  rawMetadata?: unknown
}

/** One snapshot of a community's aggregate counts, recorded at sync time. */
export interface CommunityHistoryPoint {
  recordedAt: string
  memberCount: number
  groupCount: number
  adminCount: number
  pendingRequestCount: number
}

/** One snapshot of a single group's counts, recorded at sync time. */
export interface GroupHistoryPoint {
  recordedAt: string
  memberCount: number
  pendingRequestCount: number
}

/** A group's full time series, as returned by the groups/history endpoint. */
export interface GroupHistorySeries {
  groupId: string
  groupName: string
  snapshots: GroupHistoryPoint[]
}
