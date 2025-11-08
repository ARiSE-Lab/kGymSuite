'use client';

import { useState, useEffect, useCallback } from 'react';
import { JobLog, LogsQueryParams } from '@/types';
import { useConfig } from '@/hooks/useConfig';
import { createApiClient, ApiError } from '@/lib/api';
import { LogEntry } from '@/components/log-entry';
import { Pagination } from '@/components/pagination';
import { LoadingSpinner } from '@/components/loading-spinner';
import { ErrorDisplay } from '@/components/error-display';
import { Button, Link } from '@heroui/react';

export default function JobLogsPage() {
  const { config, loading: configLoading, error: configError } = useConfig();
  const [logs, setLogs] = useState<JobLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalItems, setTotalItems] = useState(0);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const fetchLogs = useCallback(async () => {
    if (!config) return;

    try {
      setLoading(true);
      setError(null);

      const apiClient = createApiClient(config.kGymAPIEndpoint);
      const params: LogsQueryParams = {
        skip: (currentPage - 1) * pageSize,
        pageSize,
      };

      const response = await apiClient.fetchAllJobLogs(params);
      setLogs(response.page);
      setTotalItems(response.total);
    } catch (err) {
      const errorMessage = err instanceof ApiError
        ? `API Error: ${err.message}`
        : `Error: ${err instanceof Error ? err.message : 'Unknown error'}`;
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [config, currentPage, pageSize]);

  useEffect(() => {
    if (config) {
      fetchLogs();
    }
  }, [fetchLogs, config]);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1); // Reset to first page when changing page size
  };

  const handleRetry = () => {
    fetchLogs();
  };

  const handleRefresh = () => {
    setCurrentPage(1);
    fetchLogs();
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
          <h1 className="text-2xl font-bold">Job Logs</h1>
          <p className="text-default-600">
            View logs from all jobs across the system
          </p>
        </div>

        <Button
          color="primary"
          variant="flat"
          onPress={handleRefresh}
          isDisabled={loading}
        >
          Refresh
        </Button>
      </div>

      {/* Content */}
      {loading ? (
        <LoadingSpinner label="Loading job logs..." />
      ) : error ? (
        <ErrorDisplay
          title="Failed to load job logs"
          message={error}
          onRetry={handleRetry}
        />
      ) : logs.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-default-500">No job logs found</p>
        </div>
      ) : (
        <>
          {/* Logs List */}
          <div className="space-y-4">
            {logs.map((log, index) => (
              <div key={`${log.timeStamp}-${log.jobId}-${index}`} className="relative">
                <LogEntry
                  log={log}
                  showJobId={true}
                />

                {/* Job link overlay */}
                <div className="absolute top-3 right-3">
                  <Link
                    href={`/jobs/${log.jobId}`}
                    size="sm"
                    color="primary"
                    className="bg-background/80 backdrop-blur-sm px-2 py-1 rounded"
                  >
                    View Job →
                  </Link>
                </div>
              </div>
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