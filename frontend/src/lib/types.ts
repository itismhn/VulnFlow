export type Role = "admin" | "analyst" | "viewer";
export type FindingStatus =
  | "open"
  | "in_progress"
  | "fixed"
  | "reopened"
  | "risk_accepted"
  | "false_positive";
export type ScanStatus = "queued" | "parsing" | "done" | "failed";
export type ReportFormat = "pdf" | "xlsx" | "csv" | "html";
export type TemplateKind = "executive" | "technical" | "network";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface SeverityCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
}

export interface NetworkRef {
  id: number;
  name: string;
}

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  scope_restricted: boolean;
  networks: NetworkRef[];
  last_login_at: string | null;
  locked_until: string | null;
  created_at: string;
}

export interface Me extends User {
  permissions: string[];
}

export interface Scan {
  id: number;
  name: string;
  filename: string;
  size_bytes: number;
  scanner: string;
  policy_name: string;
  started_at: string | null;
  finished_at: string | null;
  status: ScanStatus;
  progress: number;
  error: string;
  host_count: number;
  finding_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  info_count: number;
  new_count: number;
  fixed_count: number;
  reopened_count: number;
  skipped_hosts: number;
  notes: string;
  archived: boolean;
  created_at: string;
  parsed_at: string | null;
  uploaded_by: { id: number; username: string } | null;
}

export interface UploadResult {
  filename: string;
  scan_id: number | null;
  duplicate_of: number | null;
  error: string | null;
}

export interface ScanHost {
  asset_id: number;
  ip: string;
  hostname: string;
  os: string;
  credentialed: boolean;
  started_at: string | null;
  counts: SeverityCounts;
}

export interface ScanDiff {
  base_scan_id: number;
  compare_scan_id: number;
  new: number;
  fixed: number;
  persisting: number;
}

export interface AssetRef {
  id: number;
  ip: string;
  hostname: string;
  fqdn: string;
  os: string;
  network_id: number | null;
}

export interface PluginBrief {
  id: number;
  name: string;
  family: string;
  cvss3_base: number | null;
  vpr_score: number | null;
  epss_score: number | null;
  exploit_available: boolean;
  cves: string[];
}

export interface Plugin extends PluginBrief {
  severity: number;
  risk_factor: string;
  synopsis: string;
  description: string;
  solution: string;
  see_also: string[];
  cvss2_base: number | null;
  cvss2_vector: string;
  cvss3_vector: string;
  cvss4_base: number | null;
  cvss4_vector: string;
  cwes: string[];
  exploit_frameworks: string[];
  exploitability_ease: string;
  publication_date: string | null;
  patch_publication_date: string | null;
  vuln_publication_date: string | null;
}

export interface UserBrief {
  id: number;
  username: string;
  full_name: string;
}

export interface Finding {
  id: number;
  asset: AssetRef;
  plugin: PluginBrief;
  port: number;
  protocol: string;
  service: string;
  severity: number;
  status: FindingStatus;
  first_seen: string;
  last_seen: string;
  fixed_at: string | null;
  reopen_count: number;
  assignee: UserBrief | null;
  due_date: string | null;
}

export interface FindingEvent {
  id: number;
  kind: "detected" | "status" | "assign" | "comment";
  from_status: string | null;
  to_status: string | null;
  note: string;
  scan_id: number | null;
  actor: UserBrief | null;
  created_at: string;
}

export interface FindingDetail extends Omit<Finding, "plugin"> {
  plugin: Plugin;
  plugin_output: string;
  occurrences: { scan_id: number; scan_name: string; observed_at: string | null; severity: number }[];
  events: FindingEvent[];
}

export type GroupBy = "host" | "plugin" | "network" | "zone" | "severity" | "status" | "port";

export interface FindingGroup {
  key: string;
  label: string;
  sublabel: string;
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
  max_severity: number;
}

export interface FindingFilters {
  q?: string;
  severity?: number[];
  status?: FindingStatus[];
  ip?: string;
  network_id?: number[];
  zone?: string[];
  asset_id?: number;
  plugin_id?: number[];
  family?: string;
  cve?: string;
  port?: number;
  exploitable?: boolean;
  min_cvss?: number;
  scan_id?: number;
  assignee_id?: number;
  overdue?: boolean;
  include_info?: boolean;
}

export interface Network {
  id: number;
  name: string;
  cidr: string;
  zone: string;
  criticality: number;
  owner: string;
  description: string;
  created_at: string;
}

export interface NetworkStats extends Network {
  asset_count: number;
  open: SeverityCounts;
}

export interface AssetRow {
  id: number;
  ip: string;
  hostname: string;
  fqdn: string;
  netbios: string;
  mac: string;
  os: string;
  criticality: number | null;
  tags: string[];
  first_seen: string | null;
  last_seen: string | null;
  network_id: number | null;
  network_name: string | null;
  zone: string | null;
  effective_criticality: number;
  risk_score: number;
  open: SeverityCounts;
}

export interface AssetScan {
  scan_id: number;
  scan_name: string;
  started_at: string | null;
  credentialed: boolean;
  findings: SeverityCounts;
}

export interface VulnRow {
  plugin_id: number;
  name: string;
  family: string;
  severity: number;
  cvss3_base: number | null;
  vpr_score: number | null;
  epss_score: number | null;
  exploit_available: boolean;
  cves: string[];
  hosts: number;
  instances: number;
}

export interface Dashboard {
  kpis: {
    open: SeverityCounts;
    exploitable: number;
    overdue: number;
    assets: number;
    assets_with_critical: number;
    scans: number;
    last_scan_at: string | null;
    new_30d: number;
    fixed_30d: number;
    mttr_days: Record<"critical" | "high" | "medium" | "low", number | null>;
  };
  trend: { date: string; critical: number; high: number; medium: number; low: number }[];
  top_hosts: {
    asset_id: number;
    ip: string;
    hostname: string;
    risk_score: number;
    critical: number;
    high: number;
  }[];
  top_vulns: {
    plugin_id: number;
    name: string;
    severity: number;
    hosts: number;
    exploit_available: boolean;
  }[];
  by_zone: { label: string; critical: number; high: number; medium: number; low: number }[];
  age: { label: string; critical: number; high: number; medium: number; low: number }[];
  status: Record<FindingStatus, number>;
}

export interface Branding {
  company_name: string;
  classification: string;
  primary_color: string;
  footer_text: string;
}

export interface TemplateConfig {
  sections: string[];
  filters: FindingFilters;
  branding: Branding;
  intro: string;
  top_n: number;
  group_by: "host" | "plugin";
}

export interface ReportTemplate {
  id: number;
  name: string;
  description: string;
  kind: TemplateKind;
  builtin: boolean;
  config: TemplateConfig;
  created_at: string;
}

export interface ReportJob {
  id: number;
  name: string;
  format: ReportFormat;
  status: "queued" | "running" | "done" | "failed";
  error: string;
  size_bytes: number;
  filters: FindingFilters;
  template: { id: number; name: string; kind: TemplateKind } | null;
  created_by: { id: number; username: string } | null;
  created_at: string;
  finished_at: string | null;
}

export interface AuditEntry {
  id: number;
  created_at: string;
  actor_id: number | null;
  actor_username: string;
  action: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  ip: string;
  user_agent: string;
}

export interface SearchHit {
  kind: "asset" | "vulnerability" | "scan";
  id: number;
  title: string;
  subtitle: string;
}
