import {
  JobsResponse,
  JobResponse,
  SystemLogsResponse,
  JobLogsResponse,
  JobsQueryParams,
  LogsQueryParams,
  JobId
} from '@/types';

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public response?: Response
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, ''); // Remove trailing slash
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
      });

      if (!response.ok) {
        throw new ApiError(
          `API request failed: ${response.status} ${response.statusText}`,
          response.status,
          response
        );
      }

      return await response.json();
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }

      throw new ApiError(
        `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    }
  }

  // Fetch jobs with pagination and sorting
  async fetchJobs(params: JobsQueryParams = {}): Promise<JobsResponse> {
    const searchParams = new URLSearchParams();

    if (params.sortBy) searchParams.set('sortBy', params.sortBy);
    if (params.skip !== undefined) searchParams.set('skip', params.skip.toString());
    if (params.pageSize !== undefined) searchParams.set('pageSize', params.pageSize.toString());

    const query = searchParams.toString();
    const endpoint = `/jobs${query ? `?${query}` : ''}`;

    return this.request<JobsResponse>(endpoint);
  }

  // Fetch specific job by ID
  async fetchJob(jobId: JobId): Promise<JobResponse> {
    return this.request<JobResponse>(`/jobs/${jobId}`);
  }

  // Fetch job-specific logs
  async fetchJobLogs(jobId: JobId, params: LogsQueryParams = {}): Promise<JobLogsResponse> {
    const searchParams = new URLSearchParams();

    if (params.skip !== undefined) searchParams.set('skip', params.skip.toString());
    if (params.pageSize !== undefined) searchParams.set('pageSize', params.pageSize.toString());

    const query = searchParams.toString();
    const endpoint = `/jobs/${jobId}/log${query ? `?${query}` : ''}`;

    return this.request<JobLogsResponse>(endpoint);
  }

  // Fetch system logs
  async fetchSystemLogs(params: LogsQueryParams = {}): Promise<SystemLogsResponse> {
    const searchParams = new URLSearchParams();

    if (params.skip !== undefined) searchParams.set('skip', params.skip.toString());
    if (params.pageSize !== undefined) searchParams.set('pageSize', params.pageSize.toString());

    const query = searchParams.toString();
    const endpoint = `/system/displays/systemLog${query ? `?${query}` : ''}`;

    return this.request<SystemLogsResponse>(endpoint);
  }

  // Fetch all job logs across the system
  async fetchAllJobLogs(params: LogsQueryParams = {}): Promise<JobLogsResponse> {
    const searchParams = new URLSearchParams();

    if (params.skip !== undefined) searchParams.set('skip', params.skip.toString());
    if (params.pageSize !== undefined) searchParams.set('pageSize', params.pageSize.toString());

    const query = searchParams.toString();
    const endpoint = `/system/displays/jobLog${query ? `?${query}` : ''}`;

    return this.request<JobLogsResponse>(endpoint);
  }

  // Fetch job tags
  async fetchJobTags(jobId: JobId): Promise<Record<string, string>> {
    return this.request<Record<string, string>>(`/jobs/${jobId}/tags`);
  }
}

// Hook to create API client with dynamic configuration
export function createApiClient(baseUrl: string): ApiClient {
  return new ApiClient(baseUrl);
}