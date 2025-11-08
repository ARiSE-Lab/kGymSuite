'use client';

import { Card, CardBody, Chip, Link } from '@heroui/react';
import { JobDigest, JobStatus } from '@/types';
import { format } from 'date-fns';

interface JobCardProps {
  job: JobDigest;
}

const statusColorMap: Record<JobStatus, 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'danger'> = {
  [JobStatus.Pending]: 'warning',
  [JobStatus.InProgress]: 'primary',
  [JobStatus.Waiting]: 'secondary',
  [JobStatus.Aborted]: 'danger',
  [JobStatus.Finished]: 'success',
};

export function JobCard({ job }: JobCardProps) {
  const formatDate = (dateStr: string) => {
    try {
      return format(new Date(dateStr), 'MMM dd, yyyy HH:mm:ss');
    } catch {
      return dateStr;
    }
  };

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardBody className="space-y-3">
        <div className="flex justify-between items-start">
          <Link
            href={`/jobs/${job.jobId}`}
            className="text-lg font-semibold text-primary hover:underline"
          >
            Job {job.jobId}
          </Link>
          <Chip
            color={statusColorMap[job.status]}
            variant="flat"
            size="sm"
          >
            {job.status}
          </Chip>
        </div>

        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-default-600">Created:</span>
            <span>{formatDate(job.createdTime)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-default-600">Modified:</span>
            <span>{formatDate(job.modifiedTime)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-default-600">Current Worker:</span>
            <span>{job.currentWorker}</span>
          </div>
          {job.currentWorkerHostname && (
            <div className="flex justify-between">
              <span className="text-default-600">Hostname:</span>
              <span className="font-mono text-xs">{job.currentWorkerHostname}</span>
            </div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}