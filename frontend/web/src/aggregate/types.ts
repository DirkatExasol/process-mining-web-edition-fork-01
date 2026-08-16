// Types for the aggregate designer (collapse connected steps into a Σ super-step).

/** One output project's destination: a name + where its data is written. */
export interface AggregateOutput {
  name: string
  /** Empty = the source connection. */
  targetConnectionId: string
  /** Empty = that connection's own schema. A new name creates the schema. */
  targetSchema: string
}

export interface CreateAggregateBody {
  connectionId: string // source connection
  members: string[]
  sigmaName: string
  highLevel: AggregateOutput
  detail: AggregateOutput
}

export interface CreateAggregateResult {
  highLevelProjectId: string
  highLevelConnectionId: string
  detailProjectId: string
  detailConnectionId: string
  sigmaStep: string
}

/** A stored Σ → detail-project link, listed for a high-level project so the app can
 *  offer drill-down on the Σ node. */
export interface AggregateLink {
  connectionId: string
  projectId: string
  sigmaStep: string
  detailConnectionId: string
  detailProjectId: string
}
