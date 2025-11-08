'use client';

import { Card, CardBody, Chip } from '@heroui/react';
import { SystemLog, JobLog } from '@/types';
import { format } from 'date-fns';
import { JsonViewer } from './json-viewer';

interface LogEntryProps {
  log: SystemLog | JobLog;
  showJobId?: boolean;
  className?: string;
}

export function LogEntry({ log, showJobId = false, className = '' }: LogEntryProps) {
  const formatDate = (dateStr: string) => {
    try {
      return format(new Date(dateStr), 'MMM dd, yyyy HH:mm:ss.SSS');
    } catch {
      return dateStr;
    }
  };

  const isJobLog = 'jobId' in log;

  return (
    <Card className={`${className}`}>
      <CardBody className="space-y-3">
        {/* Header with timestamp and metadata */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Chip
              variant="flat"
              color="primary"
              size="sm"
              className="font-mono"
            >
              {formatDate(log.timeStamp)}
            </Chip>

            <Chip
              variant="flat"
              color="secondary"
              size="sm"
            >
              {log.workerType}
            </Chip>

            {showJobId && isJobLog && (
              <Chip
                variant="flat"
                color="warning"
                size="sm"
              >
                Job: {(log as JobLog).jobId}
              </Chip>
            )}
          </div>

          <div className="text-sm text-default-600 font-mono">
            {log.workerHostname}
          </div>
        </div>

        {/* Log content */}
        <div>
          {log.content as string}
        </div>
      </CardBody>
    </Card>
  );
}