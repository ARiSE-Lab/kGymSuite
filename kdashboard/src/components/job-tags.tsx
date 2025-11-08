'use client';

import { Chip } from '@heroui/react';

interface JobTagsProps {
  tags: Record<string, string>;
  className?: string;
}

export function JobTags({ tags, className = '' }: JobTagsProps) {
  const tagEntries = Object.entries(tags);

  if (tagEntries.length === 0) {
    return (
      <div className={className}>
        <p className="text-default-500">No tags assigned to this job</p>
      </div>
    );
  }

  return (
    <div className={`space-y-2 ${className}`}>
      <div className="flex flex-wrap gap-2">
        {tagEntries.map(([key, value]) => (
          <Chip
            key={key}
            variant="flat"
            color="secondary"
            size="sm"
            classNames={{
              base: "max-w-full",
              content: "text-xs"
            }}
          >
            <span className="font-medium">{key}:</span>
            <span className="ml-1">{value}</span>
          </Chip>
        ))}
      </div>
    </div>
  );
}