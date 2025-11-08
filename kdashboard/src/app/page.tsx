'use client';

import { useState, useEffect, useCallback } from 'react';
import { JobDigest, SortingMode, JobsQueryParams } from '@/types';
import { useConfig } from '@/hooks/useConfig';
import { createApiClient, ApiError } from '@/lib/api';
import { JobCard } from '@/components/job-card';
import { Pagination } from '@/components/pagination';
import { SortControls } from '@/components/sort-controls';
import { LoadingSpinner } from '@/components/loading-spinner';
import { ErrorDisplay } from '@/components/error-display';

export default function JobsPage() {
  const { config, loading: configLoading, error: configError } = useConfig();
  const [jobs, setJobs] = useState<JobDigest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalItems, setTotalItems] = useState(0);

  // Pagination and sorting state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sortBy, setSortBy] = useState<SortingMode>('modifiedTime');

  const fetchJobs = useCallback(async () => {
    if (!config) return;

    try {
      setLoading(true);
      setError(null);

      const apiClient = createApiClient(config.kGymAPIEndpoint);
      const params: JobsQueryParams = {
        sortBy,
        skip: (currentPage - 1) * pageSize,
        pageSize,
      };

      const response = await apiClient.fetchJobs(params);
      setJobs(response.page);
      setTotalItems(response.total);
    } catch (err) {
      const errorMessage = err instanceof ApiError
        ? `API Error: ${err.message}`
        : `Error: ${err instanceof Error ? err.message : 'Unknown error'}`;
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [config, currentPage, pageSize, sortBy]);

  useEffect(() => {
    if (config) {
      fetchJobs();
    }
  }, [fetchJobs, config]);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1); // Reset to first page when changing page size
  };

  const handleSortChange = (newSortBy: SortingMode) => {
    setSortBy(newSortBy);
    setCurrentPage(1); // Reset to first page when changing sort
  };

  const handleRetry = () => {
    fetchJobs();
  };

  // Show configuration loading state
  if (configLoading) {
    return <LoadingSpinner label="Loading configuration..." />;
  }

  // Show configuration error
  if (configError) {
    return (
      <ErrorDisplay
        title="Configuration Error"
        message={configError}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold">Jobs</h1>
          <p className="text-default-600">
            Manage and monitor distributed jobs in kGym
          </p>
        </div>

        <SortControls
          sortBy={sortBy}
          onSortChange={handleSortChange}
        />
      </div>

      {/* Content */}
      {loading ? (
        <LoadingSpinner label="Loading jobs..." />
      ) : error ? (
        <ErrorDisplay
          title="Failed to load jobs"
          message={error}
          onRetry={handleRetry}
        />
      ) : jobs.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-default-500">No jobs found</p>
        </div>
      ) : (
        <>
          {/* Jobs Grid */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {jobs.map((job) => (
              <JobCard key={job.jobId} job={job} />
            ))}
          </div>

          {/* Pagination */}
          <Pagination
            currentPage={currentPage}
            totalItems={totalItems}
            pageSize={pageSize}
            onPageChange={handlePageChange}
            onPageSizeChange={handlePageSizeChange}
          />
        </>
      )}
    </div>
  );
}