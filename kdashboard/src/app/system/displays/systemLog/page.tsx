'use client';

import { useState, useEffect, useCallback } from 'react';
import { SystemLog, LogsQueryParams } from '@/types';
import { useConfig } from '@/hooks/useConfig';
import { createApiClient, ApiError } from '@/lib/api';
import { LogEntry } from '@/components/log-entry';
import { Pagination } from '@/components/pagination';
import { LoadingSpinner } from '@/components/loading-spinner';
import { ErrorDisplay } from '@/components/error-display';
import { Button } from '@heroui/react';

export default function SystemLogsPage() {
  const { config, loading: configLoading, error: configError } = useConfig();
  const [logs, setLogs] = useState<SystemLog[]>([]);
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

      const response = await apiClient.fetchSystemLogs(params);
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
          <h1 className="text-2xl font-bold">System Logs</h1>
          <p className="text-default-600">
            Monitor system-wide activity and events
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
        <LoadingSpinner label="Loading system logs..." />
      ) : error ? (
        <ErrorDisplay
          title="Failed to load system logs"
          message={error}
          onRetry={handleRetry}
        />
      ) : logs.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-default-500">No system logs found</p>
        </div>
      ) : (
        <>
          {/* Logs List */}
          <div className="space-y-4">
            {logs.map((log, index) => (
              <LogEntry
                key={`${log.timeStamp}-${index}`}
                log={log}
                showJobId={false}
              />
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