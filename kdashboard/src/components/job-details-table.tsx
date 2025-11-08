'use client';

import {
  Table,
  TableHeader,
  TableColumn,
  TableBody,
  TableRow,
  TableCell,
  Chip
} from '@heroui/react';
import { JobContext, JobStatus } from '@/types';
import { format } from 'date-fns';

interface JobDetailsTableProps {
  job: JobContext;
}

const statusColorMap: Record<JobStatus, 'default' | 'primary' | 'secondary' | 'success' | 'warning' | 'danger'> = {
  [JobStatus.Pending]: 'warning',
  [JobStatus.InProgress]: 'primary',
  [JobStatus.Waiting]: 'secondary',
  [JobStatus.Aborted]: 'danger',
  [JobStatus.Finished]: 'success',
};

export function JobDetailsTable({ job }: JobDetailsTableProps) {
  const formatDate = (dateStr: string) => {
    try {
      return format(new Date(dateStr), 'MMM dd, yyyy HH:mm:ss');
    } catch {
      return dateStr;
    }
  };

  const rows = [
    {
      key: 'jobId',
      field: 'Job ID',
      value: job.jobId,
    },
    {
      key: 'status',
      field: 'Status',
      value: (
        <Chip
          color={statusColorMap[job.status]}
          variant="flat"
          size="sm"
        >
          {job.status}
        </Chip>
      ),
    },
    {
      key: 'createdTime',
      field: 'Created Time',
      value: formatDate(job.createdTime),
    },
    {
      key: 'modifiedTime',
      field: 'Modified Time',
      value: formatDate(job.modifiedTime),
    },
    {
      key: 'currentWorker',
      field: 'Current Worker',
      value: job.currentWorker,
    },
    {
      key: 'currentWorkerHostname',
      field: 'Worker Hostname',
      value: job.currentWorkerHostname || 'N/A',
    },
    {
      key: 'totalWorkers',
      field: 'Total Workers',
      value: job.jobWorkers.length,
    },
  ];

  return (
    <Table aria-label="Job details">
      <TableHeader>
        <TableColumn>Field</TableColumn>
        <TableColumn>Value</TableColumn>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key}>
            <TableCell className="font-medium">{row.field}</TableCell>
            <TableCell>{row.value}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}