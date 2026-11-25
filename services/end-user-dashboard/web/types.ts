export type TrendPoint = { timestamp: string; count: number };
export type ServiceCount = { name: string; count: number };
export type TypeCount = { name: string; count: number };
export type HourCompare = {
  lastHour: number;
  previousHour: number;
  changePct: number | null;
  direction: 'up' | 'down' | 'flat';
};
export type CloudBreakdown = {
  providers: TypeCount[];
  regions: TypeCount[];
  platforms: TypeCount[];
  accounts: TypeCount[];
};
export type Overview = {
  total: number;
  trend: TrendPoint[];
  services: ServiceCount[];
  types?: TypeCount[];
  hourCompare?: HourCompare;
  cloud?: CloudBreakdown;
};
export type Span = {
  timestamp: string;
  serviceName: string;
  spanName: string;
  statusCode: string;
  durationNs: string;
  traceId: string;
  spanId: string;
  componentType?: string;
  cloudProvider?: string;
  cloudRegion?: string;
  cloudAvailabilityZone?: string;
  cloudPlatform?: string;
  cloudAccountId?: string;
};

export type DashboardProps = {
  overview: Overview | null;
  items: Span[];
  error: boolean;
  loading?: boolean;
  refreshing?: boolean;
  live?: boolean;
  lastUpdated?: string | null;
  refreshIntervalMs?: number;
  range?: number;
  setRange?: (n: number) => void;
  service?: string;
  setService?: (s: string) => void;
  span?: string;
  setSpan?: (s: string) => void;
  page?: number;
  setPage?: (n: number) => void;
  total?: number;
  refresh?: () => void;
};
