'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Button, Card, CardHeader, CardBody, Divider } from '@heroui/react';
import { JobContext, JobId } from '@/types';
import { useConfig } from '@/hooks/useConfig';
import { createApiClient, ApiError } from '@/lib/api';
import { JobDetailsTable } from '@/components/job-details-table';
import { WorkerTabs } from '@/components/worker-tabs';
import { JobTags } from '@/components/job-tags';
import { LoadingSpinner } from '@/components/loading-spinner';
import { ErrorDisplay } from '@/components/error-display';

export default function JobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.jobId as JobId;

  const { config, loading: configLoading, error: configError } = useConfig();
  const [job, setJob] = useState<JobContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchJob = useCallback(async () => {
    if (!config || !jobId) return;

    try {
      setLoading(true);
      setError(null);

      const apiClient = createApiClient(config.kGymAPIEndpoint);
      const response = await apiClient.fetchJob(jobId);

      if (!response) {
        setError('Job not found');
        return;
      }

      setJob(response);
    } catch (err) {
      const errorMessage = err instanceof ApiError
        ? `API Error: ${err.message}`
        : `Error: ${err instanceof Error ? err.message : 'Unknown error'}`;
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [config, jobId]);

  useEffect(() => {
    if (config && jobId) {
      fetchJob();
    }
  }, [fetchJob, config, jobId]);

  const handleRetry = () => {
    fetchJob();
  };

  const handleBack = () => {
    router.push('/');
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
          <Button
            variant="light"
            onPress={handleBack}
            className="mb-2 -ml-2"
          >
            ← Back to Jobs
          </Button>
          <h1 className="text-2xl font-bold">Job {jobId}</h1>
          <p className="text-default-600">
            Detailed view of job execution and workers
          </p>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <LoadingSpinner label="Loading job details..." />
      ) : error ? (
        <ErrorDisplay
          title="Failed to load job"
          message={error}
          onRetry={handleRetry}
        />
      ) : !job ? (
        <ErrorDisplay
          title="Job not found"
          message={`Job ${jobId} could not be found`}
        />
      ) : (
        <div className="space-y-6">
          {/* Job Details */}
          <Card>
            <CardHeader>
              <h2 className="text-xl font-semibold">Job Details</h2>
            </CardHeader>
            <Divider />
            <CardBody>
              <JobDetailsTable job={job} />
            </CardBody>
          </Card>

          {/* Job Tags */}
          {Object.keys(job.tags).length > 0 && (
            <Card>
              <CardHeader>
                <h2 className="text-xl font-semibold">Tags</h2>
              </CardHeader>
              <Divider />
              <CardBody>
                <JobTags tags={job.tags} />
              </CardBody>
            </Card>
          )}

          {/* Job Workers */}
          <Card>
            <CardHeader>
              <h2 className="text-xl font-semibold">Workers</h2>
            </CardHeader>
            <Divider />
            <CardBody>
              <WorkerTabs workers={job.jobWorkers} />
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}