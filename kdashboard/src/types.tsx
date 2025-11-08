// Job ID type - matches backend's custom JobId implementation
export type JobId = string;

// Job Status enum
export enum JobStatus {
  Pending = 'pending',
  InProgress = 'inProgress',
  Waiting = 'waiting',
  Aborted = 'aborted',
  Finished = 'finished'
}

// System Log model
export interface SystemLog {
  timeStamp: string; // ISO datetime string
  workerType: string;
  workerHostname: string;
  content: unknown; // JSON content
}

// Job Log model
export interface JobLog {
  timeStamp: string; // ISO datetime string
  jobId: JobId;
  workerType: string;
  workerHostname: string;
  content: unknown; // JSON content
}

// Job Exception model
export interface JobException {
  code: string;
  traceback: string;
  content?: unknown;
}

// Worker Exception model
export interface WorkerException {
  code: string;
  exceptionType: string;
  traceback: string;
}

// Job Resource model
export interface JobResource {
  key: string;
  storageUri: string;
}

// Job Argument model (base for worker arguments)
export interface JobArgument {
  workerType: string;
  [key: string]: unknown; // Extra fields allowed
}

// Job Result model
export interface JobResult {
  workerType: string;
  jobException?: JobException | null;
  workerException?: WorkerException | null;
  [key: string]: unknown; // Extra fields for job resources and other data
}

// Job Worker model
export interface JobWorker {
  workerType: string;
  workerArgument: JobArgument;
  workerResult?: JobResult | null;
}

// Job Digest model (summary view for job lists)
export interface JobDigest {
  jobId: JobId;
  createdTime: string; // ISO datetime string
  modifiedTime: string; // ISO datetime string
  status: JobStatus;
  currentWorkerHostname: string;
  currentWorker: number;
}

// Job Context model (full job details)
export interface JobContext {
  jobId: JobId;
  createdTime: string; // ISO datetime string
  modifiedTime: string; // ISO datetime string
  status: JobStatus;
  currentWorkerHostname: string;
  currentWorker: number;
  jobWorkers: JobWorker[];
  tags: Record<string, string>;
}

// Paginated Result wrapper
export interface PaginatedResult<T> {
  page: T[];
  pageSize: number;
  offsetNextPage: number;
  total: number;
}

// API Response types
export type JobsResponse = PaginatedResult<JobDigest>;
export type JobResponse = JobContext | null;
export type SystemLogsResponse = PaginatedResult<SystemLog>;
export type JobLogsResponse = PaginatedResult<JobLog>;

// Sorting modes for job listings
export type SortingMode = 'modifiedTime' | 'createdTime';

// API Query parameters
export interface JobsQueryParams {
  sortBy?: SortingMode;
  skip?: number;
  pageSize?: number;
}

export interface LogsQueryParams {
  skip?: number;
  pageSize?: number;
}

// Configuration type
export interface AppConfig {
  kGymAPIEndpoint: string;
}