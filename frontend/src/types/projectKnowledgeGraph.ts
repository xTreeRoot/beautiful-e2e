export type ProjectKnowledgeGraphReviewStatus = 'draft' | 'reviewed' | string;

export type KnowledgeGraphRoute = {
  id: string;
  method?: string | null;
  path?: string | null;
  summary?: string | null;
  handler?: string | null;
  source?: string | null;
  source_file?: string | null;
  source_line?: number | null;
  role?: string | null;
  produces?: string[];
  consumes?: string[];
  related_domains?: string[];
  request_body_fields?: string[];
  applicable_scenarios?: string[];
  excluded_scenarios?: string[];
  evidence?: string[];
  review_status?: string;
};

export type KnowledgeGraphModule = {
  id: string;
  source_module_id?: string | null;
  name: string;
  domain?: string | null;
  repository_id?: string;
  repository_kind?: string;
  review_status?: string;
  route_count?: number;
  entrypoint_route_ids?: string[];
  routes?: KnowledgeGraphRoute[];
  scope_boundary?: string | null;
  related_domains?: string[];
  evidence?: string[];
};

export type KnowledgeGraphRouteRef = {
  id?: string;
  method?: string | null;
  path?: string | null;
  summary?: string | null;
  source?: string | null;
  source_file?: string | null;
  source_line?: number | null;
};

export type KnowledgeGraphRelationship = {
  id: string;
  type?: string;
  variable?: string | null;
  from_route?: KnowledgeGraphRouteRef;
  to_route?: KnowledgeGraphRouteRef;
  from_module?: string | null;
  to_module?: string | null;
  confidence?: number | null;
  confirmed?: boolean;
  reason?: string | null;
  evidence?: string[];
  review_status?: string;
};

export type KnowledgeGraphPayload = {
  version?: string;
  project_id?: string;
  generated_at?: string;
  review?: {
    status?: string;
    fact_strength?: string;
    human_review_required?: boolean;
    guidance?: string;
    [key: string]: unknown;
  };
  summary?: {
    repository_count?: number;
    route_count?: number;
    module_count?: number;
    relationship_count?: number;
    review_status?: string;
    [key: string]: unknown;
  };
  modules?: KnowledgeGraphModule[];
  relationships?: KnowledgeGraphRelationship[];
  generation_policy?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ProjectKnowledgeGraph = {
  id: string;
  project_id: string;
  review_status: ProjectKnowledgeGraphReviewStatus;
  review_notes: string | null;
  graph: KnowledgeGraphPayload;
  created_at: string;
  updated_at: string;
};

export type ProjectKnowledgeGraphUpdatePayload = {
  graph: KnowledgeGraphPayload;
  review_status?: string;
  review_notes?: string | null;
  actor?: string;
};
