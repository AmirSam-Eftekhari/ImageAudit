// Mirrors the JSON contract documented in docs/api.md (produced by backend/imageaudit/api/service.py).

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

export interface Bin {
  label: string;
  count: number;
}

export interface Summary {
  id: string;
  name: string;
  root: string;
  format: string;
  created_at: string;
  duration_s: number;
  mode: "scan" | "validate";
  images_total: number;
  images_valid: number;
  annotations_total: number;
  score: number | null;
  grade: string | null;
  findings_by_severity: Partial<Record<Severity, number>>;
}

export interface Job {
  id: string;
  path: string;
  mode: string;
  source: "path" | "upload";
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  stage: string;
  done: number;
  total: number;
  progress: number;
  error: string | null;
  audit_id: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface HealthComponent {
  key: string;
  label: string;
  description: string;
  unit: string;
  weight: number;
  effective_weight: number;
  zero_at: number;
  metric: number | null;
  score: number | null;
  applicable: boolean;
  detail: Record<string, number | string>;
}

export interface Health {
  overall: number | null;
  grade: string | null;
  components: HealthComponent[];
  formula_version: string;
}

export interface Summarised {
  min: number | null;
  max: number | null;
  mean: number | null;
  median: number | null;
}

export interface SplitStat {
  split: string;
  images: number;
  valid: number;
  invalid: number;
  annotations: number;
  annotated_images: number;
  missing_labels: number;
  empty_labels: number;
}

export interface ClassStat {
  class_id: number;
  name: string;
  count: number;
  share: number;
  images: number;
  per_split: Record<string, number>;
}

export interface Statistics {
  totals: {
    images_total: number;
    images_valid: number;
    images_invalid: number;
    status_counts: Record<string, number>;
    invalid_by_status: Record<string, number>;
    annotations_total: number;
    annotation_lines_total: number;
    annotation_lines_invalid: number;
    annotated_images: number;
    empty_label_images: number;
    missing_label_images: number;
    orphan_labels: number;
    classes_declared: number;
    classes_used: number;
    annotations_per_image: number;
    total_bytes: number;
  };
  splits: SplitStat[];
  classes: ClassStat[];
  class_balance: {
    classes: number;
    unused_classes: string[];
    imbalance_ratio: number | null;
    evenness: number | null;
    max_class: string | null;
    min_class: string | null;
  };
  resolution: { top: Bin[]; unique: number; megapixels: Bin[]; width: Summarised; height: Summarised };
  aspect_ratio: Summarised & { histogram: Bin[] };
  annotation_density: Summarised & { histogram: Bin[] };
  box_size: { histogram: Bin[] };
  quality: {
    blur: Summarised & { histogram: Bin[] };
    brightness: Summarised & { histogram: Bin[] };
    contrast: Summarised & { histogram: Bin[] };
    flag_counts: Record<string, number>;
  };
  formats: Record<string, number>;
  channels: Record<string, number>;
  grayscale_images: number;
  issue_counts: Record<string, number>;
  tag_counts: Record<string, number>;
  duplicates: {
    groups: number;
    exact_groups: number;
    perceptual_groups: number;
    within_split_groups: number;
    cross_split_groups: number;
    images_in_groups: number;
    redundant_within_split: number;
    redundant_by_split: Record<string, number>;
  };
}

export interface FindingExample {
  image_id?: string;
  path?: string;
  split?: string;
  group_id?: string;
  detail?: string;
}

export interface Finding {
  id: string;
  severity: Severity;
  category: string;
  title: string;
  description: string;
  affected_count: number;
  recommendation: string;
  examples: FindingExample[];
  affected_image_ids: string[];
  affected_image_total: number;
  splits: string[];
  classes: string[];
  metric: Record<string, unknown>;
}

export interface LeakagePair {
  a: string;
  b: string;
  exact_groups: number;
  perceptual_groups: number;
  total_groups: number;
  images_a: number;
  images_b: number;
  examples: { group_id: string; kind: string }[];
}

export interface Leakage {
  applicable: boolean;
  cross_split_groups: number;
  exact_groups: number;
  perceptual_groups: number;
  leaked_images: number;
  leaked_by_split: Record<string, number>;
  eval_images: number;
  leakage_rate: number | null;
  note: string;
  pairs: LeakagePair[];
}

export interface Overview extends Summary {
  version: string;
  dataset: {
    name: string;
    root: string;
    format: string;
    class_names: string[];
    splits: string[];
    has_labels: boolean;
    notes: string[];
  };
  config: Record<string, unknown>;
  health: Health;
  statistics: Statistics;
  findings: Finding[];
  leakage: Leakage;
  issue_total: number;
}

export interface ImageItem {
  id: string;
  path: string;
  split: string;
  status: string;
  format: string | null;
  width: number | null;
  height: number | null;
  file_size: number;
  tags: string[];
  annotation_count: number;
  classes: string[];
  blur_score: number | null;
  has_preview: boolean;
}

export interface Box {
  class_id: number;
  class_name: string;
  cx: number;
  cy: number;
  w: number;
  h: number;
  line: number;
  flags: string[];
}

export interface AnnotationIssue {
  code: string;
  level: "error" | "warning" | "info";
  message: string;
  label_path: string;
  image_id: string | null;
  image_path: string | null;
  split: string;
  line: number;
  raw: string;
}

export interface ImageDetail extends ImageItem {
  sha256: string | null;
  phash: string | null;
  dhash: string | null;
  mode: string | null;
  channels: number | null;
  brightness: number | null;
  contrast: number | null;
  is_grayscale: boolean;
  error: string | null;
  label_path: string | null;
  label_status: string;
  invalid_annotation_count: number;
  boxes: Box[];
  issues: AnnotationIssue[];
  duplicate_groups: { id: string; kind: string; scope: string; size: number; splits: string[] }[];
}

export interface Page<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface ImagePage extends Page<ImageItem> {
  available_tags: string[];
  splits: string[];
  classes: string[];
}

export interface IssuePage extends Page<AnnotationIssue> {
  code_counts: Record<string, number>;
  class_names: string[];
}

export interface DupMember {
  image_id: string;
  path: string;
  split: string;
  sha256: string;
}

export interface DupGroup {
  id: string;
  kind: "exact" | "perceptual";
  scope: "within_split" | "cross_split";
  splits: string[];
  members: DupMember[];
  unique_files: number;
  max_distance: number;
}

export interface DupPage extends Page<DupGroup> {
  summary: Statistics["duplicates"];
}

export interface FindingsResponse {
  total: number;
  items: Finding[];
  categories: string[];
  splits: string[];
  classes: string[];
}

export interface HealthInfo {
  status: string;
  version: string;
  local_only: boolean;
  allowed_roots: string[];
  max_upload_bytes: number;
  report_formats: string[];
  csv_kinds: string[];
  thumbnail_sizes: number[];
}

export interface ImageQuery {
  split?: string;
  tag?: string[];
  class?: string;
  q?: string;
  finding?: string;
  sort?: string;
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}
