import type { FindingFilters, FindingStatus, GroupBy } from "./types";

/** URL search params for the findings explorer; every view is a shareable link. */
export interface FindingsSearch extends FindingFilters {
  group?: GroupBy;
  sort?: string;
  page?: number;
  finding?: number;
}

const nums = (v: unknown): number[] | undefined => {
  const arr = Array.isArray(v) ? v : v == null ? [] : [v];
  const out = arr.map(Number).filter((n) => Number.isFinite(n));
  return out.length ? out : undefined;
};
const strs = (v: unknown): string[] | undefined => {
  const arr = Array.isArray(v) ? v : v == null ? [] : [v];
  const out = arr.map(String).filter(Boolean);
  return out.length ? out : undefined;
};
const num = (v: unknown) => (v == null || v === "" || Number.isNaN(Number(v)) ? undefined : Number(v));
const str = (v: unknown) => (v == null || v === "" ? undefined : String(v));
const bool = (v: unknown) =>
  v === true || v === "true" ? true : v === false || v === "false" ? false : undefined;

const GROUPS: GroupBy[] = ["host", "plugin", "network", "zone", "severity", "status", "port"];

export function parseFindingsSearch(s: Record<string, unknown>): FindingsSearch {
  const group = str(s.group) as GroupBy | undefined;
  return {
    q: str(s.q),
    severity: nums(s.severity),
    status: strs(s.status) as FindingStatus[] | undefined,
    ip: str(s.ip),
    network_id: nums(s.network_id),
    zone: strs(s.zone),
    asset_id: num(s.asset_id),
    plugin_id: nums(s.plugin_id),
    family: str(s.family),
    cve: str(s.cve),
    port: num(s.port),
    exploitable: bool(s.exploitable),
    min_cvss: num(s.min_cvss),
    scan_id: num(s.scan_id),
    assignee_id: num(s.assignee_id),
    overdue: bool(s.overdue),
    include_info: bool(s.include_info),
    group: group && GROUPS.includes(group) ? group : undefined,
    sort: str(s.sort),
    page: num(s.page),
    finding: num(s.finding),
  };
}

export function filtersOf(s: FindingsSearch): FindingFilters {
  const { group: _g, sort: _s, page: _p, finding: _f, ...filters } = s;
  return Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== undefined)) as FindingFilters;
}

export function hasFilters(f: FindingFilters): boolean {
  return Object.values(f).some((v) => v !== undefined && !(Array.isArray(v) && v.length === 0));
}
